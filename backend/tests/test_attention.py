from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from carguito.domain.entities import Transaction
from carguito.domain.services.attention import AttentionService
from carguito.domain.value_objects.enums import TxType

USER = uuid4()


def _tx(day: date, desc: str, amount: str, **kw) -> Transaction:
    return Transaction(
        user_id=USER,
        tx_date=day,
        amount=Decimal(amount),
        raw_description=desc,
        tx_type=kw.pop("tx_type", TxType.EXPENSE),
        **kw,
    )


def _oxxo_history(start: date = date(2026, 5, 1)) -> list[Transaction]:
    """Ten ordinary OXXO charges spread over weeks — the baseline."""
    return [
        _tx(start + timedelta(days=i * 4), "OXXO SUC 4412", str(80 + (i % 3) * 10))
        for i in range(10)
    ]


def test_unusual_amount_is_judged_against_the_merchants_own_median():
    txs = _oxxo_history()
    spike = _tx(date(2026, 6, 20), "OXXO SUC 8891", "294.40")
    txs.append(spike)
    items = AttentionService().detect(txs)
    assert [i.kind for i in items] == ["unusual_amount"]
    assert items[0].transaction_id == spike.id
    assert items[0].ratio == Decimal("3.3")  # 294.40 / 90
    assert "sueles gastar" in items[0].reason
    assert items[0].severity == "warn"


def test_unusual_needs_three_prior_charges():
    txs = [
        _tx(date(2026, 6, 1), "Cafe Punta", "60"),
        _tx(date(2026, 6, 4), "Cafe Punta", "65"),
        _tx(date(2026, 6, 8), "Cafe Punta", "600"),
    ]
    assert AttentionService().detect(txs) == []


def test_window_limits_the_report_but_not_the_baseline():
    txs = _oxxo_history()
    spike = _tx(date(2026, 6, 20), "OXXO SUC 7", "400")
    txs.append(spike)
    # Window covers the spike only: it is still judged against May's charges.
    items = AttentionService().detect(txs, start=date(2026, 6, 15), end=date(2026, 6, 30))
    assert [(i.transaction_id, i.kind) for i in items] == [(spike.id, "unusual_amount")]
    # Window before the spike: nothing to report.
    assert AttentionService().detect(txs, start=date(2026, 5, 1), end=date(2026, 5, 31)) == []


def test_possible_duplicate_same_merchant_amount_within_three_days():
    a = _tx(date(2026, 6, 10), "UBER *TRIP", "187.50")
    b = _tx(date(2026, 6, 12), "UBER *TRIP", "187.50")
    far = _tx(date(2026, 7, 5), "UBER *TRIP", "187.50")
    items = AttentionService().detect([a, b, far])
    assert len(items) == 1
    assert items[0].kind == "possible_duplicate"
    assert items[0].transaction_id == b.id
    assert items[0].related_ids == (a.id,)
    assert "2 días antes" in items[0].reason


def test_weekly_series_is_not_a_duplicate():
    # A gym charged every 7 days at the same amount is a rhythm, not a double.
    txs = [_tx(date(2026, 5, 1) + timedelta(days=7 * i), "SMART FIT", "99") for i in range(8)]
    # Add a same-amount charge 2 days after one of them: still a plausible weekly hiccup.
    txs.append(_tx(date(2026, 5, 3), "SMART FIT", "99"))
    assert [i for i in AttentionService().detect(txs) if i.kind == "possible_duplicate"] == []


def test_new_merchant_only_when_large_and_ledger_is_old_enough():
    txs = _oxxo_history()  # 10 samples from May 1 to Jun 6
    early = _tx(date(2026, 5, 20), "LIVERPOOL", "4890")  # ledger only 19 days old
    late = _tx(date(2026, 6, 25), "SEARS", "4890")
    small = _tx(date(2026, 6, 26), "FARMACIA", "40")
    txs += [early, late, small]
    items = AttentionService().detect(txs)
    kinds = {i.transaction_id: i.kind for i in items}
    assert kinds.get(late.id) == "new_merchant"
    assert early.id not in kinds
    assert small.id not in kinds
    assert next(i for i in items if i.transaction_id == late.id).severity == "info"


def test_transfers_income_and_excluded_rows_never_ring():
    txs = _oxxo_history()
    txs.append(_tx(date(2026, 6, 20), "OXXO SUC 7", "900", is_transfer=True))
    txs.append(_tx(date(2026, 6, 21), "OXXO SUC 7", "900", excluded_from_stats=True))
    txs.append(_tx(date(2026, 6, 22), "OXXO SUC 7", "900", tx_type=TxType.INCOME))
    assert AttentionService().detect(txs) == []


def test_one_item_per_charge_strongest_rule_wins():
    txs = _oxxo_history()
    a = _tx(date(2026, 6, 20), "OXXO SUC 7", "400")
    b = _tx(date(2026, 6, 21), "OXXO SUC 7", "400")  # unusual AND a duplicate of a
    txs += [a, b]
    items = {i.transaction_id: i for i in AttentionService().detect(txs)}
    assert items[b.id].kind == "unusual_amount"
    assert len(items) == 2


def test_endpoint_returns_items_for_the_dev_user(app, client):
    container = app.extensions["container"]
    user = UUID(container.settings.dev_user_id)
    rows = [
        Transaction(user_id=user, tx_date=date(2026, 5, 1) + timedelta(days=i * 4),
                    amount=Decimal("90"), raw_description="OXXO SUC 1")
        for i in range(6)
    ]
    spike = Transaction(user_id=user, tx_date=date(2026, 6, 20), amount=Decimal("300"),
                        raw_description="OXXO SUC 2")
    container.transactions.add_many(rows + [spike])

    resp = client.get("/api/transactions/attention?start=2026-06-01&end=2026-06-30")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["transaction_id"] == str(spike.id)
    assert items[0]["kind"] == "unusual_amount"
    assert items[0]["ratio"] == 3.3
    assert items[0]["related_ids"] == []
