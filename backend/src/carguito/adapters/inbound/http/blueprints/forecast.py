from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, jsonify, request

from .....domain.services.forecasting import SimulationInput
from ..auth import current_user_id, get_container
from ..serialization import forecast_point_json
from ._helpers import query_int

forecast_bp = Blueprint("forecast", __name__, url_prefix="/api/forecast")


@forecast_bp.get("")
def get_forecast():
    user_id = current_user_id()
    points = get_container().get_forecast.execute(
        user_id=user_id, months=query_int("months", 12)
    )
    return jsonify(points=[forecast_point_json(p) for p in points])


@forecast_bp.post("/simulate")
def simulate():
    """Run the interactive Forecast Simulator with client-supplied sliders."""
    body = request.get_json(silent=True) or {}

    def dec(key: str, default: str = "0") -> Decimal:
        return Decimal(str(body.get(key, default)))

    sim = SimulationInput(
        starting_net_worth=dec("starting_net_worth"),
        monthly_income=dec("monthly_income"),
        monthly_expenses=dec("monthly_expenses"),
        monthly_savings_override=(
            Decimal(str(body["monthly_savings"])) if "monthly_savings" in body else None
        ),
        discretionary_spending=(
            Decimal(str(body["discretionary_spending"]))
            if "discretionary_spending" in body
            else None
        ),
        annual_return_rate=float(body.get("annual_return_rate", 0.0)),
        months=int(body.get("months", 12)),
    )
    points = get_container().simulate_forecast.execute(sim)
    return jsonify(points=[forecast_point_json(p) for p in points])
