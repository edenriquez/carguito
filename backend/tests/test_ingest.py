"""Device ingest: the file stays on the phone, only sealed text travels.

These tests seal payloads with PyNaCl exactly the way the mobile client will
(ephemeral keypair + ``crypto_box`` against the key from ``GET /api/ingest/key``),
so the wire contract of docs/custody-plan.md F1 is exercised end to end rather
than mocked. If the envelope shape ever changes, this file fails first.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json

from nacl.public import Box, PrivateKey, PublicKey
from nacl.utils import random as random_bytes

_CFDI = (
    '<?xml version="1.0"?>'
    '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
    'Total="500.00" Fecha="2024-02-10T09:00:00" TipoDeComprobante="I">'
    '<cfdi:Emisor Nombre="OXXO" Rfc="OXX999999"/>'
    "</cfdi:Comprobante>"
)

_LINES = [
    "05/01/2024 OXXO SAN RAFAEL 45.50",
    "12/01/2024 SUPER KOMPRAS CENTRO 320.00",
]


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _server_key(client) -> dict:
    return client.get("/api/ingest/key").get_json()


def _seal(payload: dict, key: dict, *, key_id: str | None = None) -> dict:
    """Build the envelope the phone sends: crypto_box + ephemeral sender key."""
    ephemeral = PrivateKey.generate()
    nonce = random_bytes(Box.NONCE_SIZE)
    box = Box(ephemeral, PublicKey(base64.b64decode(key["public_key"])))
    sealed = box.encrypt(json.dumps(payload).encode("utf-8"), nonce)
    return {
        "v": 1,
        "key_id": key_id or key["key_id"],
        "epk": _b64(bytes(ephemeral.public_key)),
        "nonce": _b64(nonce),
        "box": _b64(sealed.ciphertext),
    }


def _text_payload(lines=None, *, original: bytes = b"the pdf that stayed home") -> dict:
    return {
        "v": 1,
        "kind": "text",
        "filename": "estado_enero.pdf",
        # The hash is over the ORIGINAL file, which the server never sees.
        "content_sha256": hashlib.sha256(original).hexdigest(),
        "lines": list(_LINES if lines is None else lines),
        "xml": None,
        "extracted_at": "2026-08-16T10:00:00Z",
        "extractor": "pdfjs-4.2",
    }


def _post(client, envelope):
    return client.post("/api/ingest/extracted", json=envelope)


def test_ingest_key_publishes_the_public_half(client):
    resp = client.get("/api/ingest/key")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["algorithm"] == "x25519-xsalsa20-poly1305"
    assert len(base64.b64decode(body["public_key"])) == 32
    # key_id is short, hex and stable across calls — the phone pins it.
    assert len(body["key_id"]) == 12
    assert int(body["key_id"], 16) >= 0
    assert client.get("/api/ingest/key").get_json() == body


def test_sealed_text_becomes_transactions_custodied_on_device(client):
    key = _server_key(client)
    resp = _post(client, _seal(_text_payload(), key))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()

    assert body["template"] == "generic_bank"
    assert body["transactions_created"] == 2
    # The custody claim is on the statement itself, not just on this response.
    assert body["statement"]["source"] == "device"
    assert body["statement"]["id"] == body["statement_id"]
    assert body["statement"]["status"] == "processed"
    assert body["dashboard_url"] == f"http://localhost:3000/?statement={body['statement_id']}"

    # It landed in the same ledger a web upload would have reached.
    items = client.get("/api/transactions").get_json()["items"]
    assert {t["raw_description"] for t in items} == {"OXXO SAN RAFAEL", "SUPER KOMPRAS CENTRO"}
    assert client.get("/api/statements").get_json()["items"][0]["source"] == "device"
    assert client.get("/api/analytics/summary").get_json()["total_expense"] == 365.5


def test_sealed_cfdi_takes_the_xml_path(client):
    key = _server_key(client)
    payload = {
        "v": 1,
        "kind": "xml",
        "filename": "factura.xml",
        "content_sha256": hashlib.sha256(_CFDI.encode()).hexdigest(),
        "lines": None,
        "xml": _CFDI,
        "extracted_at": "2026-08-16T10:05:00Z",
        "extractor": "expo-file-system",
    }
    body = _post(client, _seal(payload, key)).get_json()

    assert body["template"] == "sat_cfdi"
    assert body["transactions_created"] == 1
    assert body["statement"]["source_type"] == "sat_xml"
    assert body["statement"]["source"] == "device"
    assert client.get("/api/transactions").get_json()["items"][0]["amount"] == 500.0


def test_same_content_sha256_is_a_duplicate(client):
    key = _server_key(client)
    payload = _text_payload()
    assert _post(client, _seal(payload, key)).status_code == 201
    # Re-sealed under a fresh ephemeral key, so the envelope bytes differ
    # entirely — dedup must key on the file's identity, not the ciphertext.
    assert _post(client, _seal(payload, key)).status_code == 409


def test_unknown_key_id_is_rejected(client):
    key = _server_key(client)
    envelope = _seal(_text_payload(), key, key_id="deadbeefcafe")
    resp = _post(client, envelope)
    assert resp.status_code == 400
    assert "deadbeefcafe" in resp.get_json()["detail"]


def test_garbage_box_does_not_open(client):
    key = _server_key(client)
    envelope = _seal(_text_payload(), key)
    envelope["box"] = _b64(b"not a box, just bytes")
    assert _post(client, envelope).status_code == 400

    # A box that is *almost* right — one flipped byte — must fail the same way:
    # the Poly1305 tag is the whole point.
    tampered = _seal(_text_payload(), key)
    raw = bytearray(base64.b64decode(tampered["box"]))
    raw[-1] ^= 0x01
    tampered["box"] = _b64(bytes(raw))
    assert _post(client, tampered).status_code == 400

    # And nothing was written on the way out.
    assert client.get("/api/statements").get_json()["total"] == 0


def test_malformed_payloads_are_rejected(client):
    key = _server_key(client)

    no_lines = _text_payload()
    no_lines["lines"] = None
    assert _post(client, _seal(no_lines, key)).status_code == 400

    empty_lines = _text_payload(lines=[])
    assert _post(client, _seal(empty_lines, key)).status_code == 400

    bad_kind = _text_payload()
    bad_kind["kind"] = "csv"
    assert _post(client, _seal(bad_kind, key)).status_code == 400

    bad_hash = _text_payload()
    bad_hash["content_sha256"] = "nope"
    assert _post(client, _seal(bad_hash, key)).status_code == 400

    xml_without_xml = _text_payload()
    xml_without_xml.update(kind="xml", lines=None, xml=None)
    assert _post(client, _seal(xml_without_xml, key)).status_code == 400

    old_version = _text_payload()
    old_version["v"] = 0
    assert _post(client, _seal(old_version, key)).status_code == 400


def test_malformed_envelopes_are_rejected(client):
    key = _server_key(client)

    assert client.post("/api/ingest/extracted", json=[]).status_code == 400
    assert client.post("/api/ingest/extracted", json={"v": 1}).status_code == 400

    wrong_version = _seal(_text_payload(), key)
    wrong_version["v"] = 2
    assert _post(client, wrong_version).status_code == 400

    short_nonce = _seal(_text_payload(), key)
    short_nonce["nonce"] = _b64(b"tooshort")
    assert _post(client, short_nonce).status_code == 400

    not_base64 = _seal(_text_payload(), key)
    not_base64["epk"] = "this is not base64!!"
    assert _post(client, not_base64).status_code == 400


def test_web_upload_still_declares_its_own_custody(client, sample_cfdi_bytes):
    """The honest asymmetry: the web path did receive the file, and says so."""
    created = client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    assert created.status_code == 201
    assert created.get_json()["statement"]["source"] == "web"
    assert client.get("/api/statements").get_json()["items"][0]["source"] == "web"


def test_the_two_paths_dedup_against_each_other(client):
    """One file, two surfaces, one statement: the hash means the same thing."""
    raw = _CFDI.encode()
    client.post(
        "/api/statements",
        data={"file": (io.BytesIO(raw), "factura.xml")},
        content_type="multipart/form-data",
    )
    key = _server_key(client)
    payload = {
        "v": 1,
        "kind": "xml",
        "filename": "factura.xml",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "lines": None,
        "xml": _CFDI,
        "extracted_at": "2026-08-16T10:05:00Z",
        "extractor": "expo-file-system",
    }
    assert _post(client, _seal(payload, key)).status_code == 409


def test_reuploading_a_longer_period_only_adds_what_was_missing(client):
    """A partial month uploaded early, then the closed month: complement it.

    Different files (different hashes), same account: the overlap must not
    land twice, and a movement repeated on the same day must still count.
    """
    key = _server_key(client)
    partial = _text_payload(
        ["05/01/2024 OXXO SAN RAFAEL 45.50"], original=b"enero hasta el 10"
    )
    first = _post(client, _seal(partial, key)).get_json()
    assert first["transactions_created"] == 1
    assert first["transactions_skipped"] == 0

    full = _text_payload(
        [
            "05/01/2024 OXXO  SAN RAFAEL 45.50",  # same line, rewrapped
            "05/01/2024 OXXO SAN RAFAEL 45.50",  # a second, real coffee
            "12/01/2024 SUPER KOMPRAS CENTRO 320.00",
        ],
        original=b"enero completo",
    )
    resp = _post(client, _seal(full, key))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    second = resp.get_json()
    assert second["transactions_created"] == 2
    assert second["transactions_skipped"] == 1

    items = client.get("/api/transactions").get_json()["items"]
    assert sorted(t["raw_description"] for t in items) == [
        "OXXO SAN RAFAEL",
        "OXXO SAN RAFAEL",
        "SUPER KOMPRAS CENTRO",
    ]
    assert client.get("/api/analytics/summary").get_json()["total_expense"] == 411.0


def test_complement_inherits_the_account_kind_already_declared(client):
    key = _server_key(client)
    first = _post(
        client, _seal(_text_payload(_LINES[:1], original=b"parcial"), key)
    ).get_json()
    client.patch(f"/api/statements/{first['statement_id']}", json={"account_kind": "debit"})

    second = _post(
        client, _seal(_text_payload(_LINES, original=b"completo"), key)
    ).get_json()
    assert second["transactions_skipped"] == 1
    assert second["statement"]["account_kind"] == "debit"
