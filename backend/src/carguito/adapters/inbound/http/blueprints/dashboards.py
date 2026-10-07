"""The user's composed home screen.

Only `home` for now: there is exactly one dashboard per user and naming it in
the path keeps the client from having to discover an id before it can render
anything. Additional dashboards would add `/api/dashboards` and an id route
without changing this one.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .....domain.entities import DashboardWidget
from ..auth import current_user_id, get_container
from ..serialization import dashboard_json

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/api/dashboards")


@dashboards_bp.get("/home")
def get_home():
    dashboard = get_container().get_home_dashboard.execute(user_id=current_user_id())
    return jsonify(dashboard_json(dashboard))


@dashboards_bp.put("/home")
def save_home():
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    raw_widgets = body.get("widgets")
    if not isinstance(raw_widgets, list):
        return jsonify(error="widgets must be a list"), 400

    # An unknown metric_id or a param the catalog rejects raises
    # MetricValidationError, which is a ValueError and lands on the app-wide
    # 400 handler. Failing here is the point: a layout is only saveable if it
    # is queryable.
    dashboard = get_container().save_home_dashboard.execute(
        user_id=user_id, widgets=[_widget(w, i) for i, w in enumerate(raw_widgets)]
    )
    return jsonify(dashboard_json(dashboard))


def _widget(raw, index: int) -> DashboardWidget:
    if not isinstance(raw, dict):
        raise ValueError(f"Widget at position {index} must be an object")
    metric_id = raw.get("metric_id")
    if not isinstance(metric_id, str) or not metric_id:
        raise ValueError(f"Widget at position {index} needs a string 'metric_id'")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError(f"Widget at position {index}: 'params' must be an object")

    return DashboardWidget(
        metric_id=metric_id,
        # Order comes from the array, not from a client-supplied number.
        position=index,
        size=raw.get("size") or "md",
        params=params,
        title_override=raw.get("title_override"),
    )
