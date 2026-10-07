from __future__ import annotations

from flask import Blueprint, jsonify

from ..auth import current_user_id, get_container

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.post("/cube/rebuild")
def rebuild_cube():
    """Re-derive the current user's cube rows from the relational tables.

    Scoped to the caller, not global: there is no admin role yet, and an
    endpoint that could rebuild everyone's data would be a much bigger thing to
    leave unauthenticated while ``AUTH_DISABLED=true``.
    """
    result = get_container().rebuild_cube.execute(user_id=current_user_id())
    return jsonify(user_id=str(result.user_id), rows=result.rows)
