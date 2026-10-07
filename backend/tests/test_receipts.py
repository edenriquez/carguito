"""Photographed tickets: reading them, and attaching them to the right movement.

Two things are worth guarding here and the second is the important one.

The reader is a pile of regexes over OCR output, so it gets fixtures shaped
like real Mexican tickets — a barcode before the name, the quantity on its own
line, a tax flag after the price — and the assertions are as much about what it
*refuses* (TOTAL, CAMBIO, a row of digits) as about what it finds.

The matcher decides which movement a basket belongs to, and a wrong answer
there is invisible and permanent: the receipt looks attached, the prices are
filed under the wrong day, and nothing ever says so. So the tests that matter
are the ones where it must **decline** — no total, an ambiguous pair, a
movement that already has a ticket.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from nacl.public import Box, PrivateKey, PublicKey
from nacl.utils import random as random_bytes

from tomin.domain.entities import Transaction
from tomin.domain.services.receipt_reading import read_receipt
from tomin.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")

SORIANA = [
    "SORIANA HIPER",
    "SUCURSAL MIXCOAC",
    "RFC SOR810511HN9",
    "FECHA 22/08/2026 HORA 19:42",
    "7501020510010 LECHE LALA ENT 1L 28.50 T",
    "COCA COLA 600ML",
    "2 X 20.00 40.00 T",
    "JIT SALADETTE",
    "0.850 KG X 32.00 27.20 T",
    "PAN BIMBO GRANDE 45.90 T",
    "SUBTOTAL 141.60",
    "IVA 0.00",
    "TOTAL 141.60",
    "EFECTIVO 200.00",
    "CAMBIO 58.40",
    "GRACIAS POR SU COMPRA",
]


# --- the reader ----------------------------------------------------------
def test_reads_store_date_total_and_items():
    parsed = read_receipt(SORIANA)
    assert parsed.store == "Soriana"
    assert parsed.purchased_at == date(2026, 8, 22)
    assert parsed.purchased_time == time(19, 42)
    assert parsed.total == Decimal("141.60")
    assert [i.description for i in parsed.items] == [
        "LECHE LALA ENT 1L",
        "COCA COLA 600ML",
        "JIT SALADETTE",
        "PAN BIMBO GRANDE",
    ]
    # The basket adds up to the printed total: the property the LLM reader is
    # scored on, and the one that says nothing was dropped or invented.
    assert sum(i.amount for i in parsed.items) == parsed.total


def test_quantity_line_belongs_to_the_product_above_it():
    """``COCA COLA 600ML`` / ``2 X 20.00 40.00`` is one item, not two."""
    coca = next(i for i in read_receipt(SORIANA).items if "COCA" in i.description)
    assert coca.quantity == Decimal("2")
    assert coca.unit_price == Decimal("20.00")
    assert coca.amount == Decimal("40.00")
    # The evidence keeps both printed lines.
    assert "COCA COLA 600ML" in coca.raw_text and "2 X 20.00" in coca.raw_text


def test_weight_bought_is_a_quantity_not_a_size():
    jitomate = next(i for i in read_receipt(SORIANA).items if "JIT" in i.description)
    assert jitomate.quantity == Decimal("0.850")
    assert jitomate.unit_price == Decimal("32.00")


def test_the_ticket_talking_about_itself_is_never_a_product():
    descriptions = " ".join(i.description for i in read_receipt(SORIANA).items).lower()
    for word in ("total", "iva", "efectivo", "cambio", "gracias"):
        assert word not in descriptions


def test_a_row_of_numbers_is_dropped_rather_than_guessed_at():
    """A fiscal code ending in money looks exactly like a product line."""
    parsed = read_receipt(["OXXO", "AUT 004512 55.00", "0000 1234 5678 99.00", "TOTAL 55.00"])
    assert parsed.items == []


def test_an_unreadable_photo_returns_an_empty_receipt_not_an_error():
    parsed = read_receipt(["", "   ", "|||"])
    assert parsed.items == []
    assert parsed.total is None


# --- ingest, end to end over the sealed envelope --------------------------
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _seal(client, payload: dict) -> dict:
    key = client.get("/api/ingest/key").get_json()
    ephemeral = PrivateKey.generate()
    nonce = random_bytes(Box.NONCE_SIZE)
    box = Box(ephemeral, PublicKey(base64.b64decode(key["public_key"])))
    sealed = box.encrypt(json.dumps(payload).encode("utf-8"), nonce)
    return {
        "v": 1,
        "key_id": key["key_id"],
        "epk": _b64(bytes(ephemeral.public_key)),
        "nonce": _b64(nonce),
        "box": _b64(sealed.ciphertext),
    }


def _payload(lines=None, *, photo: bytes = b"the photo that stayed home", **extra) -> dict:
    return {
        "v": 1,
        "kind": "receipt",
        "filename": "ticket.jpg",
        # Over the ORIGINAL image, which the server never sees.
        "content_sha256": hashlib.sha256(photo).hexdigest(),
        "lines": list(SORIANA if lines is None else lines),
        "captured_at": "2026-08-22T19:45:00Z",
        "extractor": "mlkit-ios",
        **extra,
    }


def _send(client, payload: dict):
    return client.post("/api/ingest/receipt", json=_seal(client, payload))


def _expense(container, *, amount: str, day: int, description: str) -> Transaction:
    tx = Transaction(
        user_id=DEV_USER,
        tx_date=date(2026, 8, day),
        amount=Decimal(amount),
        raw_description=description,
        tx_type=TxType.EXPENSE,
    )
    container.transactions.add_many([tx])
    return tx


@pytest.fixture
def container(app):
    return app.extensions["container"]


def test_sealed_receipt_becomes_a_basket_of_products(client):
    resp = _send(client, _payload())
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    receipt = body["receipt"]
    assert receipt["store"] == "Soriana"
    assert receipt["purchased_at"] == "2026-08-22"
    assert receipt["total"] == 141.60
    assert receipt["items_total"] == 141.60
    assert len(receipt["items"]) == 4
    # The photo never travelled, so provenance is all the server can say about it.
    assert receipt["extractor"] == "mlkit-ios"
    assert receipt["reader"] == "heuristic"


def test_the_same_photo_twice_is_the_same_event(client):
    assert _send(client, _payload()).status_code == 201
    assert _send(client, _payload()).status_code == 409


def test_a_matching_movement_is_attached_automatically(client, container):
    tx = _expense(container, amount="141.60", day=22, description="SORIANA HIPER 4062")
    body = _send(client, _payload()).get_json()
    assert body["attached"] is True
    assert body["receipt"]["transaction_id"] == str(tx.id)
    assert body["receipt"]["match_source"] == "auto"
    assert body["suggestions"] == []


def test_two_identical_charges_are_a_question_not_a_coin_flip(client, container):
    _expense(container, amount="141.60", day=22, description="COMPRA TIENDA A")
    _expense(container, amount="141.60", day=22, description="COMPRA TIENDA B")
    body = _send(client, _payload()).get_json()
    assert body["attached"] is False
    assert body["receipt"]["transaction_id"] is None
    # Both are offered, each with the reason it scored.
    assert len(body["suggestions"]) == 2
    assert all(s["reason"] for s in body["suggestions"])


def test_a_different_amount_is_a_different_purchase(client, container):
    _expense(container, amount="980.00", day=22, description="SORIANA HIPER 4062")
    body = _send(client, _payload()).get_json()
    assert body["attached"] is False
    assert body["suggestions"] == []


def test_a_ticket_with_no_readable_total_never_attaches(client, container):
    _expense(container, amount="141.60", day=22, description="SORIANA HIPER 4062")
    lines = [line for line in SORIANA if "TOTAL" not in line]
    body = _send(client, _payload(lines)).get_json()
    assert body["attached"] is False
    assert body["suggestions"] == []


def test_the_phone_can_name_the_movement_itself(client, container):
    tx = _expense(container, amount="141.60", day=22, description="COMPRA TIENDA A")
    _expense(container, amount="141.60", day=22, description="COMPRA TIENDA B")
    body = _send(client, _payload(transaction_id=str(tx.id))).get_json()
    assert body["receipt"]["transaction_id"] == str(tx.id)
    # A person answered, so no later automatic pass may overturn it.
    assert body["receipt"]["match_source"] == "user"


def test_a_movement_carries_at_most_one_ticket(client, container):
    tx = _expense(container, amount="141.60", day=22, description="SORIANA HIPER 4062")
    assert _send(client, _payload()).status_code == 201
    second = _send(client, _payload(photo=b"another angle", transaction_id=str(tx.id)))
    assert second.status_code == 409


def test_someone_elses_movement_is_reported_as_missing(client):
    resp = _send(client, _payload(transaction_id=str(uuid4())))
    assert resp.status_code == 404


# --- the rest of the lifecycle -------------------------------------------
def test_attach_and_detach_by_hand(client, container):
    tx = _expense(container, amount="141.60", day=22, description="COMPRA TIENDA A")
    _expense(container, amount="141.60", day=22, description="COMPRA TIENDA B")
    receipt_id = _send(client, _payload()).get_json()["receipt_id"]

    attached = client.patch(
        f"/api/receipts/{receipt_id}", json={"transaction_id": str(tx.id)}
    ).get_json()
    assert attached["transaction_id"] == str(tx.id)
    assert attached["match_source"] == "user"

    detached = client.patch(
        f"/api/receipts/{receipt_id}", json={"transaction_id": None}
    ).get_json()
    assert detached["transaction_id"] is None


def test_attaching_without_saying_to_what_is_a_bad_request(client):
    receipt_id = _send(client, _payload()).get_json()["receipt_id"]
    assert client.patch(f"/api/receipts/{receipt_id}", json={}).status_code == 400


def test_a_movement_reports_its_ticket_and_its_absence(client, container):
    tx = _expense(container, amount="141.60", day=22, description="SORIANA HIPER 4062")
    other = _expense(container, amount="12.00", day=1, description="OXXO")
    _send(client, _payload())

    found = client.get(f"/api/receipts/for-transaction/{tx.id}").get_json()
    assert found["receipt"]["store"] == "Soriana"
    # No ticket is the ordinary state of almost every row, not an error.
    empty = client.get(f"/api/receipts/for-transaction/{other.id}").get_json()
    assert empty["receipt"] is None


def test_deleting_a_statement_keeps_the_ticket_and_drops_the_link(client, container):
    """The ticket is the user's document; the statement explained a charge."""
    from tomin.domain.entities import Statement
    from tomin.domain.value_objects.enums import SourceType, StatementStatus

    statement = Statement(
        user_id=DEV_USER,
        source_type=SourceType.BANK_PDF,
        status=StatementStatus.PROCESSED,
    )
    container.statements.add(statement)
    tx = Transaction(
        user_id=DEV_USER,
        statement_id=statement.id,
        tx_date=date(2026, 8, 22),
        amount=Decimal("141.60"),
        raw_description="SORIANA HIPER 4062",
        tx_type=TxType.EXPENSE,
    )
    container.transactions.add_many([tx])
    receipt_id = _send(client, _payload()).get_json()["receipt_id"]

    assert client.delete(f"/api/statements/{statement.id}").status_code == 200

    receipt = client.get(f"/api/receipts/{receipt_id}").get_json()
    assert receipt["transaction_id"] is None
    assert len(receipt["items"]) == 4


def test_deleting_a_receipt_takes_its_items_with_it(client):
    receipt_id = _send(client, _payload()).get_json()["receipt_id"]
    assert client.delete(f"/api/receipts/{receipt_id}").status_code == 200
    assert client.get(f"/api/receipts/{receipt_id}").status_code == 404
    assert client.get("/api/receipts").get_json()["total"] == 0


# --- the web's door: a photo, read on the server -------------------------
class ScriptedOcr:
    """A ReceiptImageOcr that answers with canned rows. Never decodes anything."""

    label = "scripted-ocr"

    def __init__(self, rows):
        self.rows = rows
        self.seen: list[bytes] = []

    def read(self, image: bytes) -> list[str]:
        self.seen.append(image)
        return list(self.rows)


def _upload(client, photo: bytes = b"a jpeg of the soriana ticket", **fields):
    from io import BytesIO

    data = {"file": (BytesIO(photo), "ticket.jpg"), **fields}
    return client.post("/api/receipts/upload", data=data, content_type="multipart/form-data")


def _with_ocr(container, ocr):
    from tomin.application.use_cases import IngestReceiptImageUseCase

    container.__dict__["ingest_receipt_image"] = IngestReceiptImageUseCase(
        ocr=ocr, ingest=container.ingest_receipt
    )


def test_an_uploaded_photo_becomes_a_basket_and_is_not_kept(client, container):
    ocr = ScriptedOcr(SORIANA)
    _with_ocr(container, ocr)
    res = _upload(client, captured_at="2026-08-22T19:45:00Z")
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["receipt"]["extractor"] == "scripted-ocr"
    assert body["receipt"]["purchased_at"] == "2026-08-22"
    assert len(body["receipt"]["items"]) == 4
    # The OCR saw the bytes once; the stored receipt carries only their hash.
    assert ocr.seen == [b"a jpeg of the soriana ticket"]
    stored = client.get(f"/api/receipts/{body['receipt_id']}").get_json()
    assert "image" not in stored and stored["items_total"] == 141.6


def test_the_same_photo_uploaded_twice_is_one_ticket(client, container):
    _with_ocr(container, ScriptedOcr(SORIANA))
    assert _upload(client).status_code == 201
    assert _upload(client).status_code == 409
    assert client.get("/api/receipts").get_json()["total"] == 1


def test_a_photo_with_no_text_is_refused_not_stored(client, container):
    _with_ocr(container, ScriptedOcr([]))
    res = _upload(client, photo=b"a photo of the kitchen table")
    assert res.status_code == 422
    assert client.get("/api/receipts").get_json()["total"] == 0


def test_without_an_ocr_engine_the_upload_says_what_to_install(client, container):
    _with_ocr(container, None)
    res = _upload(client)
    assert res.status_code == 503
    assert "receipts" in res.get_json()["error"]


def test_rows_are_rejoined_across_the_two_columns():
    from tomin.adapters.outbound.receipts.ocr import _Box, group_rows

    rows = group_rows(
        [
            _Box("28.50 T", top=102, left=600, height=20),
            _Box("LECHE LALA ENT 1L", top=100, left=40, height=22),
            _Box("COCA COLA 600ML", top=140, left=40, height=22),
            _Box("40.00 T", top=143, left=600, height=20),
        ]
    )
    assert rows == ["LECHE LALA ENT 1L 28.50 T", "COCA COLA 600ML 40.00 T"]


# --- the model-backed reader ---------------------------------------------
class ScriptedChat:
    """A ChatPort that returns one canned answer. Never touches the network."""

    available = True
    model_label = "fake/model"

    def __init__(self, answer: str) -> None:
        self._answer = answer

    def stream(self, *, system, messages, options=None):
        yield self._answer


def _llm(answer: str):
    from tomin.adapters.outbound.receipts import LlmReceiptReader

    return LlmReceiptReader(ScriptedChat(answer))


def test_a_model_read_that_adds_up_wins():
    """The heuristic drops the two-line item; a better read replaces it."""
    answer = json.dumps(
        {
            "store": "SORIANA HIPER",
            "purchased_at": "2026-08-22",
            "total": "141.60",
            "items": [
                {"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50"},
                {"line_no": 5, "description": "COCA COLA 600ML", "amount": "40.00",
                 "quantity": "2", "unit_price": "20.00"},
                {"line_no": 7, "description": "JITOMATE SALADETTE", "amount": "27.20"},
                {"line_no": 9, "description": "PAN BIMBO GRANDE", "amount": "45.90"},
            ],
        }
    )
    parsed = _llm(answer).read(SORIANA)
    assert parsed.reader == "llm:fake/model"
    assert [i.description for i in parsed.items][2] == "JITOMATE SALADETTE"
    # The evidence stays the OCR line, not the model's paraphrase of it.
    assert parsed.items[2].raw_text == "JIT SALADETTE"


def test_a_model_read_that_does_not_add_up_loses_to_the_regexes():
    """Two items missing is a worse read, however confident the prose."""
    answer = json.dumps(
        {
            "store": "SORIANA",
            "total": "141.60",
            "items": [{"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50"}],
        }
    )
    parsed = _llm(answer).read(SORIANA)
    assert parsed.reader == "heuristic"
    assert len(parsed.items) == 4


def test_the_date_at_the_foot_wins_over_an_earlier_one():
    """Bodega Aurrerá prints the sale's date and time at the foot; a
    promotion's expiry higher up is a date too, but it has no clock."""
    parsed = read_receipt(
        [
            "BODEGA AURRERA",
            "PROMOCION VALIDA HASTA 31/12/2026",
            "LECHE LALA ENT 1L 28.50",
            "TOTAL 28.50",
            "TC 0451 AUT 004512",
            "28/09/26          14:32",
        ]
    )
    assert parsed.purchased_at == date(2026, 9, 28)
    assert parsed.purchased_time == time(14, 32)


def test_a_tax_marker_glued_to_the_price_is_not_part_of_it():
    """The camera reads the ``T``/``A`` after a price as a digit stuck to
    the cents; ``14.001`` is fourteen pesos, not a fourteen-thousandth."""
    parsed = read_receipt(
        [
            "BODEGA AURRERA",
            "1501052476960 CJ CHIPOTLE 14.001",
            "1506995002930 GV TAMARIND 3.504",
            "TOTAL 17.50",
        ]
    )
    assert [(i.description, str(i.amount)) for i in parsed.items] == [
        ("CJ CHIPOTLE", "14.00"),
        ("GV TAMARIND", "3.50"),
    ]


def test_a_walmart_ticket_as_the_camera_reads_it():
    """Rows straight from a photo: barcodes glued to names, zeros for O's,
    Walmart's price-times-quantity, a department header joined onto a row,
    the TOTAL read as words, and the card slip's IMPORTE carrying the figure."""
    parsed = read_receipt(
        [
            "mi BodegaAurrera TOTAL",
            "ARTICULO CANT.",
            "7501030452553PAN ARTESA 61.00T",
            "7501017004270 C0ST FRIJO 13.50x2 27.00T",
            "31BOLILLO 1.90×6 11.40T",
            "QUESOSYEMBUTIDOS- 7501040007934CHX T0CINO 57.00T",
            "40112PLATANOCHIA 0.675KGSX17.00/KG 11.48T",
            "Rebaja 1x$46-14.00x 46.00T",
            "SUBTOTAL 83.44",
            "UNMIL TOTAL QUINIENTOS SIETEPESOS 40/100M",
            "TARJETA:Mastercard IMP0RTE:$1,507.40",
            "26/09/26 15:23",
        ]
    )
    assert parsed.store == "Mi Bodega Aurrera"
    assert parsed.total == Decimal("1507.40")
    assert parsed.purchased_at == date(2026, 9, 26)
    assert [(i.description, str(i.amount), i.quantity, i.unit_price) for i in parsed.items] == [
        ("PAN ARTESA", "61.00", None, None),
        ("COST FRIJO", "27.00", Decimal("2"), Decimal("13.50")),
        ("BOLILLO", "11.40", Decimal("6"), Decimal("1.90")),
        ("CHX TOCINO", "57.00", None, None),
        ("PLATANOCHIA", "11.48", Decimal("0.675"), Decimal("17.00")),
    ]


def test_a_discount_under_an_item_is_the_price_it_cost():
    parsed = read_receipt(
        [
            "BODEGA AURRERA",
            "7501040083136LVI MANCH 60.00T",
            "Rebaja 1x$46-14.00x 46.00T",
            "7509552963663 FRUCTIS SH 122.00x1 122.00A",
            "02MBCOMBINA-49.50X 72.50A",
            "TOTAL 118.50",
        ]
    )
    assert [(i.description, str(i.amount)) for i in parsed.items] == [
        ("LVI MANCH", "46.00"),
        ("FRUCTIS SH", "72.50"),
    ]


def test_a_price_whose_name_the_camera_lost_still_counts():
    """A crease took the names; the prices are real and the basket adds up."""
    from tomin.domain.services.products import UNREADABLE_LINE, product_key

    parsed = read_receipt(
        [
            "WALMART",
            "MASCOTAS 55.00A",
            "20.00A",
            "7502002873376 PERRO 10KG 784.00A",
            "SUBTOTAL 859.00",
            "991.06",
            "TOTAL 859.00",
        ]
    )
    # "MASCOTAS 55.00A" is the department header the camera glued onto the
    # first item's price: a price with no name, like the bare "20.00A".
    assert [(i.description, str(i.amount)) for i in parsed.items] == [
        (UNREADABLE_LINE, "55.00"),
        (UNREADABLE_LINE, "20.00"),
        ("PERRO 10KG", "784.00"),
    ]
    assert product_key(UNREADABLE_LINE) == ""


def test_a_dotted_thousands_total_reads_whole():
    parsed = read_receipt(["WALMART", "PAN 15.00T", "TARJETA IMP0RTE:$1.575.68"])
    assert parsed.total == Decimal("1575.68")


def test_ocr_zeros_do_not_split_one_product_into_two():
    from tomin.domain.services.products import product_key

    assert product_key("C0ST FRIJ0") == product_key("COST FRIJO")
    assert product_key("D0L0RES AC") == product_key("DOLORES AC")
    # Real digits stay: a size is a size.
    assert product_key("LALA 900G") == product_key("LALA 900 G")


def test_department_headers_and_bare_arithmetic_are_not_products():
    """A header glued to a price is a product whose name the camera lost;
    a header joined onto a product row is words to take off it; arithmetic
    and a label-less subtotal are neither."""
    from tomin.domain.services.products import UNREADABLE_LINE

    parsed = read_receipt(
        [
            "WALMART",
            "ABARROTES PROCESADOS 5.00A",
            "7501079011261 ITAL PASTA 37.00T",
            "LACTEOS",
            "QUIMICOS- 7509546684253AXN VIN 64 32.00A",
            "7509552849523FRUCTIS TR TOCADOR- 74.00A",
            "38.00 x 114.00A",
            "S 1,415.74",
            "TOTAL 151.00",
        ]
    )
    assert [(i.description, str(i.amount)) for i in parsed.items] == [
        (UNREADABLE_LINE, "5.00"),
        ("ITAL PASTA", "37.00"),
        ("AXN VIN 64", "32.00"),
        ("FRUCTIS TR", "74.00"),
    ]


def test_two_rows_joined_keep_the_amount_the_arithmetic_names():
    parsed = read_receipt(["WALMART", "7501045400846 D0L0RES AC 42.00×2 84.00T 74.00C", "TOTAL 158.00"])
    assert [(i.description, str(i.amount), i.quantity) for i in parsed.items] == [
        ("DOLORES AC", "84.00", Decimal("2")),
    ]


def test_a_model_price_that_is_not_on_the_cited_line_is_dropped():
    """Asked for a number, a model reading noise produces one; only prices
    whose digits are on the ticket survive."""
    answer = json.dumps(
        {
            "store": "SORIANA HIPER",
            "purchased_at": "2026-08-22",
            "purchased_time": "19:42",
            "total": "141.60",
            "items": [
                {"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50"},
                # The name line; the arithmetic is on the line under it.
                {"line_no": 5, "description": "COCA COLA 600ML", "amount": "40.00",
                 "quantity": "2", "unit_price": "20.00"},
                {"line_no": 8, "description": "JITOMATE SALADETTE", "amount": "27.20"},
                {"line_no": 9, "description": "PAN BIMBO GRANDE", "amount": "45.90"},
                # No 12.00 anywhere near line 9: a price the model made up.
                {"line_no": 9, "description": "SALSA VALENTINA", "amount": "12.00"},
            ],
        }
    )
    parsed = _llm(answer).read(SORIANA)
    assert parsed.reader == "llm:fake/model"
    assert [i.description for i in parsed.items] == [
        "LECHE LALA ENT 1L",
        "COCA COLA 600ML",
        "JITOMATE SALADETTE",
        "PAN BIMBO GRANDE",
    ]


def test_a_date_spelled_with_a_month_name_and_an_ocr_space():
    parsed = read_receipt(["OXXO", "PAN 15.00", "TOTAL 15.00", "28 /SEP/ 26  09:05"])
    assert parsed.purchased_at == date(2026, 9, 28)
    assert parsed.purchased_time == time(9, 5)


def test_a_model_that_forgets_the_date_keeps_the_one_the_regexes_found():
    answer = json.dumps(
        {
            "store": "SORIANA HIPER",
            "purchased_at": None,
            "purchased_time": None,
            "total": "141.60",
            "items": [
                {"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50"},
                {"line_no": 5, "description": "COCA COLA 600ML", "amount": "40.00",
                 "quantity": "2", "unit_price": "20.00"},
                {"line_no": 7, "description": "JITOMATE SALADETTE", "amount": "27.20"},
                {"line_no": 9, "description": "PAN BIMBO GRANDE", "amount": "45.90"},
            ],
        }
    )
    parsed = _llm(answer).read(SORIANA)
    assert parsed.reader == "llm:fake/model"
    assert parsed.purchased_at == date(2026, 8, 22)
    assert parsed.purchased_time == time(19, 42)


def test_an_answer_cut_short_keeps_the_items_it_finished():
    """A model out of tokens stops mid-item; the complete ones still count."""
    answer = (
        '{"store": "SORIANA HIPER", "purchased_at": "2026-08-22", "purchased_time": "19:42",'
        ' "total": "141.60", "items": ['
        '{"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50"},'
        '{"line_no": 5, "description": "COCA COLA 600ML", "amount": "40.00", "quantity": "2", "unit_price": "20.00"},'
        '{"line_no": 7, "description": "JITOMATE SALADETTE", "amount": "27.20"},'
        '{"line_no": 9, "description": "PAN BIMBO GRANDE", "amount": "45.90"},'
        '{"line_no": 12, "descr'
    )
    parsed = _llm(answer).read(SORIANA)
    assert parsed.reader == "llm:fake/model"
    assert [i.description for i in parsed.items] == [
        "LECHE LALA ENT 1L",
        "COCA COLA 600ML",
        "JITOMATE SALADETTE",
        "PAN BIMBO GRANDE",
    ]


def test_an_answer_that_is_not_json_is_not_an_error():
    parsed = _llm("Claro, aquí está tu ticket: leche, coca…").read(SORIANA)
    assert parsed.reader == "heuristic"
    assert len(parsed.items) == 4


def test_an_empty_basket_never_wins():
    """A model that returned nothing failed to read; it did not prove emptiness."""
    parsed = _llm(json.dumps({"store": None, "total": None, "items": []})).read(SORIANA)
    assert len(parsed.items) == 4


def test_the_model_is_asked_with_numbered_lines():
    """`line_no` is only answerable if the prompt says which line is which."""
    chat = ScriptedChat("{}")
    sent = []

    def stream(*, system, messages, options=None):
        sent.extend(messages)
        yield "{}"

    chat.stream = stream
    from tomin.adapters.outbound.receipts import LlmReceiptReader

    LlmReceiptReader(chat).read(SORIANA)
    assert "4: 7501020510010 LECHE LALA ENT 1L 28.50 T" in sent[0].content
