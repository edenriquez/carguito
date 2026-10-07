"""Self-transfers the wording rules cannot see: taught parties + mirror pairs.

The failure mode these features exist for: a user who moves money between
their own accounts sees those moves counted as real income AND real spending,
and their cumulative net goes negative while their actual life is fine. The
assertions that matter are the boundaries — a human's answer is never
overturned, third-party lookalikes are never absorbed, and teaching once
covers the next upload too.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from carguito.domain.entities import Transaction
from carguito.domain.services.transfers import TransferPartyService, pair_transfers
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


def _tx(
    desc: str,
    amount: str,
    tx_type: TxType = TxType.EXPENSE,
    day: int = 10,
    statement_id: UUID | None = None,
    **kw,
) -> Transaction:
    return Transaction(
        user_id=DEV_USER,
        tx_date=date(2026, 5, day),
        amount=Decimal(amount),
        raw_description=desc,
        tx_type=tx_type,
        statement_id=statement_id or uuid4(),
        **kw,
    )


# --- TransferPartyService ---------------------------------------------------


def test_party_matches_through_bank_formatting_noise():
    service = TransferPartyService(["eduardo yael enriquez tapia"])
    # One taught name must cover every bank's spelling of it: case, accents
    # AND punctuation are formatting noise, not identity.
    assert service.is_own("EDUARDO YAEL,ENRIQUEZ/TAPIA Transferencia interbancaria")
    assert service.is_own("Eduardo Yael Enríquez Tapia Transferencia")


def test_party_does_not_match_third_parties():
    service = TransferPartyService(["eduardo enriquez"])
    assert not service.is_own("TRANSFERENCIA SPEI ENVIADA MARIA LOPEZ")
    assert not service.is_own("RENTA DEPTO ABRIL")


# --- pair_transfers ---------------------------------------------------------


def test_mirror_pair_found_across_statements():
    out = _tx("EDUARDO B AZTECA Transferencia", "6500", TxType.EXPENSE, day=14)
    into = _tx("TRANSFERENCIA SPEI A SU FAVOR", "6500", TxType.INCOME, day=14)
    pairs = pair_transfers([out, into])
    assert pairs == [(out, into)]


def test_no_pair_when_gap_exceeds_window():
    out = _tx("Transferencia enviada", "1000", TxType.EXPENSE, day=1)
    into = _tx("TRANSFERENCIA SPEI A SU FAVOR", "1000", TxType.INCOME, day=9)
    assert pair_transfers([out, into]) == []


def test_no_pair_within_the_same_statement():
    sid = uuid4()
    out = _tx("Transferencia enviada", "1000", TxType.EXPENSE, statement_id=sid)
    into = _tx("Transferencia recibida", "1000", TxType.INCOME, statement_id=sid)
    assert pair_transfers([out, into]) == []


def test_no_pair_without_transfer_wording():
    # Same amount, opposite directions, days apart — but a grocery charge and
    # a salary line are a coincidence, not a mirror.
    out = _tx("OXXO SUC 4412", "500", TxType.EXPENSE)
    into = _tx("ABONO NOMINA", "500", TxType.INCOME)
    assert pair_transfers([out, into]) == []


def test_each_leg_pairs_at_most_once():
    out1 = _tx("Transferencia enviada", "5000", TxType.EXPENSE, day=14)
    out2 = _tx("Transferencia enviada", "5000", TxType.EXPENSE, day=14)
    into = _tx("Transferencia recibida", "5000", TxType.INCOME, day=14)
    assert len(pair_transfers([out1, out2, into])) == 1


def test_anchored_mirror_confirms_the_unflagged_leg():
    # The Nu side got flagged by a taught party; the Azteca side must not stay
    # "income" just because its twin was understood first.
    out = _tx("EDUARDO B AZTECA Transferencia", "6500", TxType.EXPENSE, day=14, is_transfer=True)
    into = _tx("TRANSFERENCIA SPEI A SU FAVOR", "6500", TxType.INCOME, day=15)
    assert pair_transfers([out, into]) == [(out, into)]


def test_anchor_confirms_at_most_one_mirror():
    anchor = _tx("Transferencia enviada", "500", TxType.EXPENSE, day=14, is_transfer=True)
    in1 = _tx("TRANSFERENCIA SPEI A SU FAVOR", "500", TxType.INCOME, day=14)
    in2 = _tx("TRANSFERENCIA SPEI A SU FAVOR", "500", TxType.INCOME, day=15)
    assert len(pair_transfers([anchor, in1, in2])) == 1


def test_user_locked_rows_are_never_paired():
    out = _tx(
        "Transferencia enviada", "1000", TxType.EXPENSE, transfer_source="user"
    )
    into = _tx("Transferencia recibida", "1000", TxType.INCOME)
    assert pair_transfers([out, into]) == []


# --- use cases through the API ----------------------------------------------


@pytest.fixture
def ledger(app):
    """Nu-shaped history: two self-sends, one third-party SPEI, one mirror."""
    container = app.extensions["container"]
    rows = [
        _tx("Eduardo Yael Enriquez Tapia Transferencia", "30000", TxType.EXPENSE, day=3),
        _tx("Eduardo Yael Enriquez Tapia Transferencia", "14950", TxType.EXPENSE, day=17),
        _tx("TRANSFERENCIA SPEI ENVIADA MARIA LOPEZ", "8000", TxType.EXPENSE, day=5),
        _tx("EDUARDO B AZTECA Transferencia", "6500", TxType.EXPENSE, day=14),
        _tx("TRANSFERENCIA SPEI A SU FAVOR", "6500", TxType.INCOME, day=15),
    ]
    container.transactions.add_many(rows)
    container.cube.upsert_transactions(rows)
    return rows


def test_mark_transfer_dry_run_reports_blast_radius(client, ledger):
    resp = client.post(
        "/api/transactions/mark-transfer",
        json={"party": "Eduardo Yael Enriquez Tapia", "dry_run": True},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["matched"] == 2
    assert body["updated"] == 0


def test_mark_transfer_flags_learns_and_spares_third_parties(client, app, ledger):
    resp = client.post(
        "/api/transactions/mark-transfer",
        json={"party": "Eduardo Yael Enriquez Tapia"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated"] == 2

    container = app.extensions["container"]
    flagged = {
        t.raw_description: t.is_transfer
        for t in container.transactions.iter_for_user(DEV_USER)
    }
    assert flagged["Eduardo Yael Enriquez Tapia Transferencia"] is True
    assert flagged["TRANSFERENCIA SPEI ENVIADA MARIA LOPEZ"] is False

    # The teaching is remembered for the next upload.
    assert container.user_transfer_parties.list_for_user(DEV_USER) == [
        "eduardo yael enriquez tapia"
    ]


def test_pair_transfers_endpoint_flags_both_legs(client, app, ledger):
    dry = client.post("/api/transactions/pair-transfers", json={"dry_run": True})
    assert dry.get_json() == {"pairs": 1, "updated": 0}

    real = client.post("/api/transactions/pair-transfers", json={})
    assert real.get_json() == {"pairs": 1, "updated": 2}

    container = app.extensions["container"]
    by_desc = {
        t.raw_description: t for t in container.transactions.iter_for_user(DEV_USER)
    }
    assert by_desc["EDUARDO B AZTECA Transferencia"].is_transfer
    assert by_desc["TRANSFERENCIA SPEI A SU FAVOR"].is_transfer
    assert not by_desc["TRANSFERENCIA SPEI ENVIADA MARIA LOPEZ"].is_transfer


def test_patch_is_transfer_locks_against_automatic_passes(client, app, ledger):
    container = app.extensions["container"]
    mirror_out = next(
        t
        for t in container.transactions.iter_for_user(DEV_USER)
        if t.raw_description == "EDUARDO B AZTECA Transferencia"
    )

    # The user says: this one is NOT a transfer (say, a gift to a namesake).
    resp = client.patch(
        f"/api/transactions/{mirror_out.id}", json={"is_transfer": False}
    )
    assert resp.status_code == 200
    assert resp.get_json()["transfer_source"] == "user"

    # The pairing pass now finds nothing: the locked leg is out of bounds.
    assert client.post("/api/transactions/pair-transfers", json={}).get_json()["pairs"] == 0

    # And mark-transfer refuses to overturn the human too.
    client.post("/api/transactions/mark-transfer", json={"party": "eduardo b azteca"})
    refreshed = container.transactions.get(mirror_out.id)
    assert refreshed.is_transfer is False


def test_patch_is_transfer_true_clears_cash_withdrawal(client, app):
    container = app.extensions["container"]
    tx = _tx("RETIRO CAJERO AZTECA", "2000", TxType.EXPENSE)
    tx.is_cash_withdrawal = True
    container.transactions.add_many([tx])

    resp = client.patch(f"/api/transactions/{tx.id}", json={"is_transfer": True})
    body = resp.get_json()
    assert body["is_transfer"] is True
    assert body["is_cash_withdrawal"] is False


def test_taught_party_flags_future_uploads(client, app, sample_cfdi_bytes):
    """End-to-end memory check through a real ingest.

    A CFDI parses into one OXXO expense; teach "oxxo" as a party first and the
    ingest pipeline must land the new row already flagged. (Nobody would teach
    that in real life — it is the cheapest fixture that exercises the seam.)
    """
    container = app.extensions["container"]
    container.user_transfer_parties.add(DEV_USER, "oxxo")

    resp = client.post(
        "/api/statements",
        data={"file": (sample_cfdi_bytes, "factura.xml")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201

    rows = list(container.transactions.iter_for_user(DEV_USER))
    assert len(rows) == 1
    assert rows[0].is_transfer is True
