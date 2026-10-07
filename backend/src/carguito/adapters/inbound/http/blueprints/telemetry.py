"""Interaction telemetry: the client says what was touched, we keep it.

Deliberately dumb. The client batches events and posts them; this validates
the shape, stamps the user, and stores. No sampling, no derived metrics here --
the point is to *have the rows* when the question "how do people work through
Movimientos" is asked, and to answer it then with a query, not now with a guess.

Only the owner reads their own events back, aggregated. Nothing here is ever
sent to a third party.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from ..auth import current_user_id, get_container
from ._helpers import query_int

telemetry_bp = Blueprint("telemetry", __name__, url_prefix="/api/telemetry")

MAX_BATCH = 200
MAX_PROPS = 12


@telemetry_bp.post("/events")
def record_events():
    body = request.get_json(silent=True) or {}
    raw = body.get("events")
    if not isinstance(raw, list) or not raw:
        return jsonify(error="events must be a non-empty list"), 400
    if len(raw) > MAX_BATCH:
        return jsonify(error=f"at most {MAX_BATCH} events per batch"), 400

    events = []
    for item in raw:
        cleaned = _event(item)
        if cleaned is None:
            return jsonify(error="each event needs name, path and occurred_at"), 400
        events.append(cleaned)

    stored = get_container().ui_events.add_many(current_user_id(), events)
    return jsonify(stored=stored), 201


@telemetry_bp.get("/events")
def recent_events():
    """The raw rows behind the heat view, newest first, over the last ``days``.

    UTC timestamps with an explicit ``Z``: the browser turns them into the
    user's own hours, which is the only clock an hour-of-day heat strip is
    honest in.
    """
    days = max(1, min(query_int("days", 30), 365))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    items = get_container().ui_events.recent(current_user_id(), since)
    return jsonify(days=days, items=items, total=len(items))


@telemetry_bp.get("/summary")
def summary():
    """What this user touched, counted, over the last ``days`` (default 30)."""
    days = max(1, min(query_int("days", 30), 365))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rows = get_container().ui_events.summary(current_user_id(), since)
    return jsonify(
        days=days,
        items=[{"name": n, "path": p, "count": c} for n, p, c in rows],
        total=sum(c for _, _, c in rows),
    )


def _event(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    name, path, when = item.get("name"), item.get("path"), item.get("occurred_at")
    if not (isinstance(name, str) and 0 < len(name) <= 80):
        return None
    if not (isinstance(path, str) and 0 < len(path) <= 200):
        return None
    try:
        occurred = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if occurred.tzinfo is not None:
        occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
    props = item.get("props") or {}
    if not isinstance(props, dict) or len(props) > MAX_PROPS:
        return None
    # Flat and small: a prop is a label, not a payload.
    props = {
        str(k)[:40]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:80])
        for k, v in props.items()
    }
    return {"name": name, "path": path, "occurred_at": occurred, "props": props}
