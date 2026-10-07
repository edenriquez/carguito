"""The ledger's first and last day — what the time filter anchors on."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from carguito.domain.entities import Transaction
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


def test_an_empty_ledger_has_no_span(client):
    assert client.get("/api/transactions/span").get_json() == {"first": None, "last": None}


def test_the_span_is_the_oldest_and_newest_transaction(client, app):
    container = app.extensions["container"]
    container.transactions.add_many([
        Transaction(user_id=DEV_USER, tx_date=date(2026, 6, 3), amount=Decimal("10"),
                    raw_description="A", tx_type=TxType.EXPENSE),
        Transaction(user_id=DEV_USER, tx_date=date(2026, 8, 26), amount=Decimal("10"),
                    raw_description="B", tx_type=TxType.EXPENSE),
        Transaction(user_id=DEV_USER, tx_date=date(2026, 7, 15), amount=Decimal("10"),
                    raw_description="C", tx_type=TxType.EXPENSE),
    ])
    assert client.get("/api/transactions/span").get_json() == {
        "first": "2026-06-03", "last": "2026-08-26",
    }
