from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from ..auth import current_user_id, get_container
from ..serialization import (
    category_spend_json,
    monthly_point_json,
    spending_summary_json,
)
from ._helpers import query_date, query_int

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@analytics_bp.get("/summary")
def summary():
    user_id = current_user_id()
    result = get_container().spending_summary.execute(
        user_id=user_id, start=query_date("start"), end=query_date("end")
    )
    return jsonify(spending_summary_json(result))


@analytics_bp.get("/spending-by-category")
def spending_by_category():
    user_id = current_user_id()
    rows = get_container().cube.spending_by_category(
        user_id, query_date("start"), query_date("end")
    )
    return jsonify(items=[category_spend_json(c) for c in rows])


@analytics_bp.get("/monthly")
def monthly():
    user_id = current_user_id()
    rows = get_container().cube.monthly_series(user_id, months=query_int("months", 12))
    return jsonify(items=[monthly_point_json(m) for m in rows])


@analytics_bp.get("/recurring")
def recurring():
    user_id = current_user_id()
    statement_ids = [UUID(v) for v in request.args.getlist("statement_id")]
    items = get_container().detect_recurring.execute(
        user_id=user_id, statement_ids=statement_ids or None
    )
    return jsonify(
        items=[
            {
                "key": i.key,
                "label": i.label,
                "occurrences": i.occurrences,
                "frequency": i.frequency,
                "typical_amount": float(i.typical_amount),
                "monthly_equivalent": float(i.monthly_equivalent),
                "amount_stable": i.amount_stable,
                "last_date": i.last_date,
                "next_expected": i.next_expected,
                "category_id": i.category_id,
                "charges": [
                    {"date": c.date, "amount": float(c.amount)} for c in i.charges
                ],
            }
            for i in items
        ]
    )
