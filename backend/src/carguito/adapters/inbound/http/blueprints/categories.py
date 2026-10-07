from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from .....application.use_cases.update_transaction import UnknownCategoryError
from ..auth import get_container

categories_bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _category_json(c) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "color": c.color,
        "icon": c.icon,
        "parent_id": str(c.parent_id) if c.parent_id else None,
    }


@categories_bp.get("")
def list_categories():
    """The category catalog: id, display name, color, icon, parent_id.

    Global reference data, not user data — every account shares one taxonomy
    today. `parent_id` is null on a root; a child points at its root. One
    level only. `categorization_labels` stays server-side on purpose: it is
    the matcher's internal vocabulary, not something a client should render
    or depend on.
    """
    items = get_container().categories.get_all()
    return jsonify(items=[_category_json(c) for c in items])


@categories_bp.post("")
def create_category():
    """Mint a leaf under a root. Same name under the same parent is a no-op
    and returns the sibling that already exists — Afinar's Enter on a
    typed match must not duplicate.
    """
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    parent_id = body.get("parent_id")
    if not name or not parent_id:
        return jsonify(error="Provide 'name' and 'parent_id'"), 400
    try:
        parent_uuid = UUID(str(parent_id))
    except ValueError:
        return jsonify(error="parent_id must be a uuid"), 400
    try:
        category = get_container().create_category.execute(
            name=str(name), parent_id=parent_uuid
        )
    except UnknownCategoryError as err:
        return jsonify(error="Category not found", detail=str(err)), 404
    return jsonify(_category_json(category)), 201
