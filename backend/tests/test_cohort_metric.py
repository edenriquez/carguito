"""``cohort_profile`` end to end, through POST /api/metrics/query.

``test_cohort.py`` proves the rhythm arithmetic. This proves the resolver wires
it to the right rows: that the caller's rule reaches both sub-queries, that the
ledger defaults still apply through a resolver, and -- the one that matters most
-- that a set too small to describe comes back with nulls rather than zeros.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from carguito.domain.entities import Transaction
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")

ALL_TIME = {"start": "2000-01-01", "end": "2100-01-01"}


def _add(app, txs):
    container = app.extensions["container"]
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return txs


def _tx(day: date, amount: str, description: str, **kw) -> Transaction:
    return Transaction(
        user_id=DEV_USER,
        tx_date=day,
        amount=Decimal(amount),
        raw_description=description,
        tx_type=kw.pop("tx_type", TxType.EXPENSE),
        **kw,
    )


def _profile(client, filters=None, period=ALL_TIME):
    resp = client.post(
        "/api/metrics/query",
        json={
            "period": period,
            "queries": [{"key": "p", "metric": "cohort_profile", "filters": filters or {}}],
        },
    )
    assert resp.status_code == 200
    entry = resp.get_json()["results"]["p"]
    assert "error" not in entry, entry
    return entry


@pytest.fixture
def topups(app):
    """Twenty weekly 15-peso top-ups plus one 200-peso plan, and an Uber.

    Long enough and numerous enough that the rhythm is stated rather than
    withheld -- the fixture exists to exercise the honest path.
    """
    start = date(2024, 1, 1)
    txs = [_tx(start + timedelta(days=7 * i), "15", "TELCEL RECARGA") for i in range(20)]
    txs.append(_tx(start + timedelta(days=30), "200", "RECARGA PLAN TELCEL"))
    txs.append(_tx(start + timedelta(days=3), "450", "UBER TRIP"))
    return _add(app, txs)


# --- the honest path ------------------------------------------------------
def test_profile_describes_the_set_the_rule_names(client, topups):
    row = _profile(client, {"description_contains": "recarga"})["rows"][0]

    assert row["count"] == 21
    assert Decimal(row["total"]) == Decimal("500")  # 20*15 + 200; no Uber
    # Quantized to centavos like every other peso figure in the envelope:
    # 500/21 is 23.8095..., and a mean carried to nine places is false precision.
    assert Decimal(row["mean"]) == Decimal("23.81")
    # The median describes the habit; the mean is dragged up by the one plan.
    assert Decimal(row["median"]) == Decimal("15")
    assert Decimal(row["min"]) == Decimal("15")
    assert Decimal(row["max"]) == Decimal("200")


def test_rhythm_is_stated_when_the_set_can_carry_it(client, topups):
    entry = _profile(client, {"description_contains": "recarga"})
    assert entry["meta"]["partial"] is False
    row = entry["rows"][0]
    assert row["per_week"] is not None
    assert row["per_month"] is not None
    # Weekly top-ups, with one extra landing between two of them.
    assert Decimal(row["median_days_between"]) <= Decimal(7)


def test_the_rule_reaches_both_sub_queries(client, topups):
    # The distribution comes from `cohort_totals` and the rhythm from
    # `cohort_activity`. If the filters reached only one of them, the count
    # here would disagree with the total -- which is the exact desync this
    # resolver exists to prevent.
    row = _profile(client, {"description_contains": "uber"})["rows"][0]
    assert row["count"] == 1
    assert Decimal(row["total"]) == Decimal("450")
    assert Decimal(row["max"]) == Decimal("450")


def test_amount_bounds_narrow_the_profile(client, topups):
    row = _profile(client, {"description_contains": "recarga", "amount_max": 50})["rows"][0]
    assert row["count"] == 20
    assert Decimal(row["total"]) == Decimal("300")
    assert Decimal(row["max"]) == Decimal("15")


def test_exclude_tx_narrows_the_profile(client, topups):
    plan = str(topups[20].id)
    row = _profile(
        client, {"description_contains": "recarga", "exclude_tx": [plan]}
    )["rows"][0]
    assert row["count"] == 20
    assert Decimal(row["max"]) == Decimal("15")


def test_the_period_scopes_the_profile(client, topups):
    # Unlike advice, a cohort reading is about the window the user is looking
    # at. The first four weekly top-ups fall in January.
    jan = {"start": "2024-01-01", "end": "2024-01-31"}
    row = _profile(client, {"description_contains": "recarga"}, period=jan)["rows"][0]
    assert row["count"] == 6  # 5 weekly (1,8,15,22,29) + the plan on the 31st


# --- what it refuses to say ----------------------------------------------
def test_an_empty_set_is_nulls_not_zeros(client, topups):
    entry = _profile(client, {"description_contains": "no-existe-esto"})
    row = entry["rows"][0]

    assert row["count"] == 0
    assert entry["meta"]["partial"] is True
    # A confident $0 is a claim about someone's finances. Absence of data is
    # not (docs/redesign-plan.md §4).
    assert row["total"] is None
    assert row["mean"] is None
    assert row["median"] is None
    assert row["per_week"] is None
    assert row["median_days_between"] is None


def test_an_empty_set_still_returns_one_row(client, topups):
    # Zero rows is indistinguishable from a metric that failed. The frame has
    # to be able to say "ningun movimiento cumple esta regla".
    assert len(_profile(client, {"description_contains": "nada"})["rows"]) == 1


def test_too_short_a_history_withholds_the_rate_but_keeps_the_total(app, client):
    _add(app, [_tx(date(2024, 5, d), "15", "RECARGA") for d in (1, 3, 5, 8, 11, 14, 17)])
    entry = _profile(client, {"description_contains": "recarga"})
    row = entry["rows"][0]

    assert entry["meta"]["partial"] is True
    assert row["count"] == 7
    # The totals are exact and survive the partial verdict; only the rates are
    # withheld. "Necesitas 2 meses. Llevas 1." is the frame's job, not a made-up
    # per-month figure.
    assert Decimal(row["total"]) == Decimal("105")
    assert row["per_month"] is None
    assert row["per_week"] is None


def test_too_few_movements_withholds_the_rate(app, client):
    _add(app, [_tx(date(2024, m, 1), "15", "RECARGA") for m in (1, 3, 6)])
    entry = _profile(client, {"description_contains": "recarga"})
    assert entry["meta"]["partial"] is True
    assert entry["rows"][0]["per_week"] is None
    assert Decimal(entry["rows"][0]["total"]) == Decimal("45")


# --- the ledger defaults still apply through a resolver -------------------
def test_transfers_and_excluded_rows_stay_out(app, client):
    _add(
        app,
        [_tx(date(2024, 1, 1) + timedelta(days=7 * i), "15", "RECARGA") for i in range(10)]
        + [
            _tx(date(2024, 2, 1), "9999", "RECARGA", excluded_from_stats=True),
            _tx(date(2024, 2, 2), "8888", "RECARGA PAGO TC", is_transfer=True),
        ],
    )
    row = _profile(client, {"description_contains": "recarga"})["rows"][0]

    # Both loud rows match the rule by wording and are still absent: the
    # measure-level defaults are declared once in the vocabulary and inherited
    # here by construction, not re-remembered in the resolver.
    assert row["count"] == 10
    assert Decimal(row["total"]) == Decimal("150")
    assert Decimal(row["max"]) == Decimal("15")


def test_income_is_not_part_of_a_spend_profile(app, client):
    _add(
        app,
        [_tx(date(2024, 1, 1) + timedelta(days=7 * i), "15", "RECARGA") for i in range(10)]
        + [_tx(date(2024, 2, 5), "7777", "RECARGA REEMBOLSO", tx_type=TxType.INCOME)],
    )
    row = _profile(client, {"description_contains": "recarga"})["rows"][0]
    assert row["count"] == 10
    # MIN/MAX/MEDIAN have no signed form; if the income row leaked in, `max`
    # would be 7777 rather than 15.
    assert Decimal(row["max"]) == Decimal("15")


# --- the sibling metrics --------------------------------------------------
def test_cohort_activity_carries_the_count_beside_the_total(client, topups):
    resp = client.post(
        "/api/metrics/query",
        json={
            "period": ALL_TIME,
            "queries": [
                {
                    "key": "a",
                    "metric": "cohort_activity",
                    "grain": "month",
                    "filters": {"description_contains": "recarga"},
                }
            ],
        },
    )
    rows = resp.get_json()["results"]["a"]["rows"]
    assert rows, "the chart needs its months"
    # 260 pesos is four top-ups or one plan. A chart that cannot tell them
    # apart is decoration.
    assert all("expense_amount" in r and "tx_count" in r for r in rows)
    assert sum(int(Decimal(r["tx_count"])) for r in rows) == 21
