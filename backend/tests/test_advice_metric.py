"""``financial_advice`` end to end, through POST /api/metrics/query.

The unit matrix lives in test_advisor.py; what these cover is the wiring the
unit tests cannot see -- that the resolver reads the *same* monthly series the
`monthly_cash_flow` widget does (transfers and excluded rows already removed by
the measure's default filters), and that a short history degrades to
`meta.partial` rather than to an empty card.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from carguito.domain.entities import Transaction
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


def _month(index: int) -> date:
    return date(2024, index, 15)


def _seed(app, months, **kwargs):
    """One income and one expense row per month. `months` is (income, expense)."""
    container = app.extensions["container"]
    txs = []
    for index, (income, expense) in enumerate(months, start=1):
        txs.append(
            Transaction(
                user_id=DEV_USER,
                tx_date=_month(index),
                amount=Decimal(str(income)),
                raw_description="Nomina",
                tx_type=TxType.INCOME,
                **kwargs,
            )
        )
        txs.append(
            Transaction(
                user_id=DEV_USER,
                tx_date=_month(index),
                amount=Decimal(str(expense)),
                raw_description="Super",
                tx_type=TxType.EXPENSE,
            )
        )
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return txs


def _advice(client):
    resp = client.post(
        "/api/metrics/query",
        json={"queries": [{"key": "a", "metric": "financial_advice"}]},
    )
    assert resp.status_code == 200
    return resp.get_json()["results"]["a"]


# --- active ---------------------------------------------------------------
def test_active_advice_carries_the_users_own_numbers(app, client):
    _seed(app, [(20000, 8000)] * 5 + [(30000, 8000)])

    entry = _advice(client)
    assert entry["shape"] == "table"
    assert entry["meta"]["partial"] is False

    (row,) = entry["rows"]
    assert row["principle_id"] == "P1"
    assert row["active"] is True
    assert row["month"] == "2024-06"
    assert row["suggested_amount"] == "10000.00"
    assert row["months_of_history"] == 6
    # The baseline is in the sentence: the advisor never shows a number the
    # user cannot check.
    assert "20,000" in row["reason"]
    assert "30,000" in row["reason"]


def test_transfers_do_not_inflate_the_peak_month(app, client):
    """The resolver goes through the aggregation path, so `is_transfer` applies.

    A card payment booked as income in the last month would otherwise fabricate
    a peak and fire the advice on money that never arrived.
    """
    _seed(app, [(20000, 8000)] * 6)
    fake_peak = [
        Transaction(
            user_id=DEV_USER,
            tx_date=_month(6),
            amount=Decimal(50000),
            raw_description="Traspaso entre cuentas",
            tx_type=TxType.INCOME,
            is_transfer=True,
        )
    ]
    app.extensions["container"].transactions.add_many(fake_peak)
    app.extensions["container"].cube.upsert_transactions(fake_peak)

    (row,) = _advice(client)["rows"]
    assert row["active"] is False


# --- dormant --------------------------------------------------------------
def test_dormant_when_the_latest_month_is_ordinary(app, client):
    _seed(app, [(20000, 8000)] * 6)

    entry = _advice(client)
    assert entry["meta"]["partial"] is False

    (row,) = entry["rows"]
    assert row["active"] is False
    assert row["suggested_amount"] is None
    # Dormant is still the principle, rendered quietly -- not an empty card.
    assert row["phrase"]
    assert row["reason"]


# --- insufficient history -------------------------------------------------
def test_three_months_of_history_is_partial_not_empty(app, client):
    _seed(app, [(20000, 8000), (20000, 8000), (90000, 8000)])

    entry = _advice(client)
    assert entry["meta"]["partial"] is True

    (row,) = entry["rows"]
    assert row["active"] is False
    assert row["months_of_history"] == 3


def test_no_transactions_at_all_still_returns_the_principle(client):
    entry = _advice(client)
    assert entry["meta"]["partial"] is True
    (row,) = entry["rows"]
    assert row["months_of_history"] == 0
    assert row["month"] is None


# --- period independence --------------------------------------------------
@pytest.mark.parametrize(
    "period",
    [{"start": "2024-01-01", "end": "2024-01-31"}, {"start": "2024-06-01", "end": "2024-06-30"}],
)
def test_the_dashboard_period_never_narrows_the_baseline(app, client, period):
    """`ignores_period`: advice is a claim about the latest month, always.

    Scoped to January the series would be one month; scoped to June it would be
    one month with no baseline. Either way the card would say something else
    than what it claims to say.
    """
    _seed(app, [(20000, 8000)] * 5 + [(30000, 8000)])

    resp = client.post(
        "/api/metrics/query",
        json={"period": period, "queries": [{"key": "a", "metric": "financial_advice"}]},
    )
    (row,) = resp.get_json()["results"]["a"]["rows"]
    assert row["active"] is True
    assert row["months_of_history"] == 6
