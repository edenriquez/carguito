from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ....application.dtos.analytics import CategorySpend, MonthlyPoint, SpendingSummary
from ....application.dtos.attention import AttentionDTO
from ....application.dtos.metrics import MetricError, MetricResult
from ....domain.entities import (
    Conversation,
    ConversationTurn,
    Dashboard,
    DashboardWidget,
    Goal,
    Receipt,
    ReceiptItem,
    Statement,
    Tag,
    Transaction,
    Workstation,
)
from ....domain.metrics.spec import MetricSpec
from ....domain.services.forecasting import ForecastPoint
from ....domain.services.prices import PricePoint, ProductPrices


def _num(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def attention_json(a: AttentionDTO) -> dict:
    return {
        "transaction_id": a.transaction_id,
        "kind": a.kind,
        "reason": a.reason,
        "ratio": float(a.ratio) if a.ratio is not None else None,
        "related_ids": list(a.related_ids),
        "severity": a.severity,
    }


def transaction_json(t: Transaction) -> dict:
    return {
        "id": str(t.id),
        "statement_id": str(t.statement_id) if t.statement_id else None,
        "date": _iso(t.tx_date),
        "description": t.description,
        "raw_description": t.raw_description,
        "amount": _num(t.amount),
        "currency": t.currency,
        "type": t.tx_type.value,
        "status": t.status.value,
        "category_id": str(t.category_id) if t.category_id else None,
        "merchant_id": str(t.merchant_id) if t.merchant_id else None,
        "category_source": t.category_source,
        "notes": t.notes,
        "excluded_from_stats": t.excluded_from_stats,
        # Derived facts, serialized so client-side aggregates (the Flujo
        # chart) can honor the same ledger rules the cube does.
        "is_transfer": t.is_transfer,
        "transfer_source": t.transfer_source,
        "is_cash_withdrawal": t.is_cash_withdrawal,
        "tag_ids": [str(tag_id) for tag_id in t.tag_ids],
    }


def tag_json(t: Tag) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "color": t.color,
        "kind": t.kind,
        "created_at": _iso(t.created_at),
    }


def statement_json(s: Statement) -> dict:
    return {
        "id": str(s.id),
        "source_type": s.source_type.value,
        "bank": s.bank,
        "period_start": _iso(s.period_start),
        "period_end": _iso(s.period_end),
        "status": s.status.value,
        "account_kind": s.account_kind.value if s.account_kind else None,
        # What the card statement asks to be paid, or null when the text did
        # not carry it (every debit statement, and any card the reader missed).
        "credit_no_interest_payment": _money(s.credit_no_interest_payment),
        "credit_minimum_payment": _money(s.credit_minimum_payment),
        "credit_due_date": _iso(s.credit_due_date),
        # Custody, published so the UI can say the true thing per statement:
        # "device" means the file never left the phone.
        "source": s.source.value,
        "uploaded_at": _iso(s.uploaded_at),
    }


def category_spend_json(c: CategorySpend) -> dict:
    return {
        "category_id": c.category_id,
        "category_name": c.category_name,
        "amount": _num(c.amount),
        "percentage": c.percentage,
    }


def monthly_point_json(m: MonthlyPoint) -> dict:
    return {"month": m.month, "income": _num(m.income), "expense": _num(m.expense)}


def spending_summary_json(s: SpendingSummary) -> dict:
    return {
        "total_income": _num(s.total_income),
        "total_expense": _num(s.total_expense),
        "top_category": s.top_category,
        "by_category": [category_spend_json(c) for c in s.by_category],
        "monthly": [monthly_point_json(m) for m in s.monthly],
    }


def forecast_point_json(p: ForecastPoint) -> dict:
    return {
        "month_offset": p.month_offset,
        "baseline": _num(p.baseline_net_worth),
        "optimized": _num(p.optimized_net_worth),
    }


def metric_spec_json(spec: MetricSpec) -> dict:
    """The catalog as data: everything the widget picker needs before querying.

    ``kind`` is deliberately omitted -- whether a metric compiles to SQL or runs
    a Python function is an implementation fact, and publishing it would let a
    client couple to it and block the migration later.
    """
    return {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "group": spec.group,
        "shape": spec.shape,
        "unit": spec.unit,
        "dimensions": list(spec.dimensions),
        "filters": list(spec.filters),
        "grains": list(spec.grains),
        "default_dimensions": list(spec.default_dimensions),
        "default_grain": spec.default_grain,
        "cumulative": spec.cumulative,
        # `null` unless the metric rests on a heuristic. The frame renders the
        # tag off this field, so it never has to know which metric it holds.
        "quality": spec.quality,
        "ignores_period": spec.ignores_period,
        "requires": list(spec.requires),
        "params": [
            {
                "name": p.name,
                "type": p.type,
                "required": p.required,
                # Decimals reach JSON as strings, like every other money value.
                "default": None if p.default is None else str(p.default),
                "minimum": p.minimum,
                "maximum": p.maximum,
            }
            for p in spec.params
        ],
    }


def metric_result_json(result: MetricResult) -> dict:
    return {
        "metric": result.metric_id,
        "shape": result.shape,
        "unit": result.unit,
        "value": result.value,
        "rows": result.rows,
        "meta": {
            "currency": result.meta.currency,
            "overlapping": result.meta.overlapping,
            "partial": result.meta.partial,
            "source_txn_count": result.meta.source_txn_count,
        },
    }


def metric_error_json(error: MetricError) -> dict:
    return {
        "error": {
            "metric": error.metric_id,
            "code": error.code,
            "message": error.message,
        }
    }


def metric_entry_json(entry: MetricResult | MetricError) -> dict:
    return (
        metric_error_json(entry)
        if isinstance(entry, MetricError)
        else metric_result_json(entry)
    )


def dashboard_widget_json(w: DashboardWidget) -> dict:
    return {
        "id": str(w.id),
        "metric_id": w.metric_id,
        "position": w.position,
        "size": w.size,
        "params": w.params,
        "title_override": w.title_override,
    }


def dashboard_json(d: Dashboard) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "is_default": d.is_default,
        "updated_at": _iso(d.updated_at),
        "widgets": [dashboard_widget_json(w) for w in d.widgets],
    }


def workstation_json(w: Workstation) -> dict:
    """A lens as the client sees it.

    `filters` is the rule already translated into a metric query. It is derived,
    not stored, but it ships anyway: without it every client would reimplement
    `WorkstationRule.to_filters`, and the day one of them disagreed about what
    "between 10 and 300" means, the chart and the tiles would quietly describe
    different sets.
    """
    return {
        "id": str(w.id),
        "name": w.name,
        "rule": w.rule.to_json(),
        "excluded_tx_ids": [str(i) for i in w.excluded_tx_ids],
        "filters": w.to_filters(),
        "created_at": _iso(w.created_at),
        "updated_at": _iso(w.updated_at),
    }


def conversation_json(c: Conversation) -> dict:
    return {
        "id": str(c.id),
        "workstation_id": str(c.workstation_id),
        "title": c.title,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def conversation_turn_json(t: ConversationTurn) -> dict:
    return {
        "id": str(t.id),
        "role": t.role,
        "content": t.content,
        "created_at": _iso(t.created_at),
    }


def goal_json(g: Goal) -> dict:
    return {
        "id": str(g.id),
        "name": g.name,
        "target_amount": _num(g.target_amount),
        "current_amount": _num(g.current_amount),
        "target_date": _iso(g.target_date),
        "progress": round(g.progress, 4),
    }


def _money(value: Decimal | None) -> float | None:
    """Like :func:`_num`, but ``None`` survives.

    Receipts are full of prices that are genuinely unknown — a loose bolillo
    has no unit price — and ``0.0`` would render as "free" on every screen that
    reads this. The absence has to travel.
    """
    return float(value) if value is not None else None


def receipt_item_json(i: ReceiptItem) -> dict:
    return {
        "id": str(i.id),
        "line_no": i.line_no,
        # The OCR line behind every other field here, so the UI can show the
        # user what it read before it interpreted anything.
        "raw_text": i.raw_text,
        "description": i.description,
        "product_key": i.product_key,
        "amount": _num(i.amount),
        "quantity": _money(i.quantity),
        "unit_price": _money(i.unit_price),
        "size": _money(i.size),
        "size_unit": i.size_unit,
        # Derived, and null far more often than not (see the entity).
        "each": _money(i.each),
        "per_base_unit": _money(i.per_base_unit),
    }


def receipt_json(r: Receipt) -> dict:
    return {
        "id": str(r.id),
        "transaction_id": str(r.transaction_id) if r.transaction_id else None,
        "match_source": r.match_source,
        "store": r.store,
        "purchased_at": _iso(r.purchased_at),
        "total": _money(r.total),
        "currency": r.currency,
        # Provenance: which OCR engine read the photo and which reader
        # structured the lines. Shown in the detail panel, because a basket
        # that came out wrong is a different conversation depending on these.
        "extractor": r.extractor,
        "reader": r.reader,
        "captured_at": _iso(r.captured_at),
        "created_at": _iso(r.created_at),
        # What the lines add up to. The UI compares it against `total` and says
        # so when they disagree — OCR drops lines, and a silently short basket
        # is worse than a visible gap.
        "items_total": _num(r.items_total),
        "items": [receipt_item_json(i) for i in r.items],
    }


def price_point_json(point: PricePoint, basis: str) -> dict:
    return {
        "receipt_id": str(point.receipt_id),
        "transaction_id": str(point.transaction_id) if point.transaction_id else None,
        "purchased_at": _iso(point.purchased_at),
        # The photo's own timestamp: the fallback date for a ticket whose
        # print had none the reader could use.
        "captured_at": _iso(point.captured_at),
        "store": point.store,
        "description": point.description,
        "amount": _num(point.amount),
        "quantity": _money(point.quantity),
        "each": _money(point.each),
        "per_base_unit": _money(point.per_base_unit),
        "size": _money(point.size),
        "size_unit": point.size_unit,
        # The figure this product is actually compared by, already chosen by
        # the domain so no client re-decides it and gets a different answer.
        "value": _money(point.value(basis)),
    }


def product_prices_json(p: ProductPrices, *, include_points: bool = True) -> dict:
    """One product's price history.

    ``include_points`` off is the list view: a pantry of 300 products would
    otherwise ship every purchase of every one of them to draw 300 summary
    rows. The detail endpoint turns it back on.
    """
    body = {
        "product_key": p.product_key,
        "name": p.name,
        # "unit" (per litre/kilo) or "each" (per piece). Every figure below is
        # in this basis, and the UI must say which — "$18 vs $32" means nothing
        # if one of them was three times the size.
        "basis": p.basis,
        "times_bought": p.times_bought,
        "priced": p.priced,
        "median": _money(p.median),
        "spread": _money(p.spread),
        "latest_vs_median": _money(p.latest_vs_median),
        "stores": list(p.stores),
        "cheapest": price_point_json(p.cheapest, p.basis) if p.cheapest else None,
        "dearest": price_point_json(p.dearest, p.basis) if p.dearest else None,
        "latest": price_point_json(p.latest, p.basis) if p.latest else None,
    }
    if include_points:
        body["points"] = [price_point_json(point, p.basis) for point in p.points]
    return body
