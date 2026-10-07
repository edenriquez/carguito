"""The generic metric surface: one catalog endpoint, one batched query endpoint.

Batched because the command center renders N widgets and N round trips per
period change is not a design. Results are keyed by the client's widget key and
each key is independently a result *or* an error -- a broken metric returns an
error object under its key with the request still 200, so the other widgets
render.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request

from .....application.dtos.metrics import MetricQuery, Period
from ..auth import current_user_id, get_container
from ..serialization import metric_entry_json, metric_spec_json

metrics_bp = Blueprint("metrics", __name__, url_prefix="/api/metrics")


@metrics_bp.get("")
def catalog():
    specs = get_container().metric_catalog.execute()
    return jsonify(items=[metric_spec_json(s) for s in specs])


@metrics_bp.post("/query")
def run_queries():
    body = request.get_json(silent=True) or {}
    # user_id comes from the session, never the payload. It is not in the
    # filter vocabulary either, so a client naming it gets a rejected filter
    # rather than a tenant switch.
    user_id = current_user_id()

    default_period = _period(body.get("period"))
    raw_queries = body.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        return jsonify(error="queries must be a non-empty list"), 400

    # A malformed *envelope* is a 400 for the whole request; a well-formed query
    # naming something the catalog rejects is a per-key error further down.
    queries = [_query(item, default_period) for item in raw_queries]

    batch = get_container().run_metric_queries.execute(user_id=user_id, queries=queries)
    return jsonify(results={key: metric_entry_json(v) for key, v in batch.results.items()})


def _period(raw) -> Period:
    if not isinstance(raw, dict):
        return Period()
    return Period(start=_date(raw.get("start")), end=_date(raw.get("end")))


def _date(value) -> date | None:
    return date.fromisoformat(value) if value else None


def _query(raw, default_period: Period) -> MetricQuery:
    if not isinstance(raw, dict):
        raise ValueError("Each query must be an object")
    key, metric = raw.get("key"), raw.get("metric")
    if not isinstance(key, str) or not key:
        raise ValueError("Each query needs a string 'key'")
    if not isinstance(metric, str) or not metric:
        raise ValueError(f"Query '{key}' needs a string 'metric'")

    dimensions = raw.get("dimensions") or []
    if not isinstance(dimensions, list) or not all(isinstance(d, str) for d in dimensions):
        raise ValueError(f"Query '{key}': 'dimensions' must be a list of strings")
    filters = raw.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError(f"Query '{key}': 'filters' must be an object")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError(f"Query '{key}': 'params' must be an object")

    return MetricQuery(
        key=key,
        metric=metric,
        dimensions=tuple(dimensions),
        filters=filters,
        grain=raw.get("grain"),
        # A widget may override the dashboard-wide period (a 12-month trend
        # next to a this-month breakdown).
        period=_period(raw["period"]) if isinstance(raw.get("period"), dict) else default_period,
        params=params,
    )
