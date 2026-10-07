from __future__ import annotations

from datetime import date

from flask import request


def query_date(name: str) -> date | None:
    value = request.args.get(name)
    if not value:
        return None
    return date.fromisoformat(value)


def query_int(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
