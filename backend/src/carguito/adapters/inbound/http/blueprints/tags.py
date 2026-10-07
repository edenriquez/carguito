"""Tag CRUD plus the two tagging gestures (docs/redesign-plan.md §7, B6).

``PUT /api/transactions/{id}/tags`` replaces one transaction's list; ``POST
/api/tags/{id}/transactions`` adds one tag to many transactions. Replace and
add-to-many are different operations on purpose -- bulk tagging must not strip
tags the selected rows already carry.
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from .....application.ports.outbound import DuplicateTagError
from .....application.use_cases.tags import UNSET
from ..auth import current_user_id, get_container
from ..serialization import tag_json

tags_bp = Blueprint("tags", __name__, url_prefix="/api/tags")

#: Mirrors the transaction patch: only declared fields are writable, and an
#: unrecognised key is a 400 rather than a silent no-op.
_PATCHABLE = {"name", "color", "kind"}


@tags_bp.get("")
def list_tags():
    user_id = current_user_id()
    items = get_container().manage_tags.list(user_id=user_id)
    return jsonify(items=[tag_json(t) for t in items], total=len(items))


@tags_bp.post("")
def create_tag():
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return jsonify(error="name is required"), 400
    try:
        tag = get_container().manage_tags.create(
            user_id=user_id,
            name=body["name"],
            color=body.get("color"),
            kind=body.get("kind", "plain"),
        )
    except DuplicateTagError as err:
        # 409 rather than the ValueError handler's 400: the request is
        # well-formed, it collides with state that already exists.
        return jsonify(error="Tag already exists", detail=str(err)), 409
    return jsonify(tag_json(tag)), 201


@tags_bp.patch("/<tag_id>")
def update_tag(tag_id: str):
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    unknown = set(body) - _PATCHABLE
    if unknown:
        return jsonify(error=f"Unsupported fields: {sorted(unknown)}"), 400
    try:
        tag = get_container().manage_tags.update(
            user_id=user_id,
            tag_id=UUID(tag_id),
            name=body.get("name", UNSET),
            color=body.get("color", UNSET),
            kind=body.get("kind", UNSET),
        )
    except DuplicateTagError as err:
        return jsonify(error="Tag already exists", detail=str(err)), 409
    return jsonify(tag_json(tag))


@tags_bp.delete("/<tag_id>")
def delete_tag(tag_id: str):
    user_id = current_user_id()
    untagged = get_container().manage_tags.delete(user_id=user_id, tag_id=UUID(tag_id))
    # The transactions survive; only the annotation is gone.
    return jsonify(tag_id=tag_id, transactions_untagged=untagged)


@tags_bp.post("/<tag_id>/transactions")
def tag_transactions(tag_id: str):
    """Attach one tag to many transactions. Additive, never a replacement."""
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    ids = _uuid_list(body, "transaction_ids")
    tagged = get_container().manage_tags.attach_to_transactions(
        user_id=user_id, tag_id=UUID(tag_id), transaction_ids=ids
    )
    return jsonify(tag_id=tag_id, transactions_tagged=tagged)


def _uuid_list(body: dict, key: str) -> list[UUID]:
    raw = body.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"'{key}' must be a list of ids")
    return [UUID(value) for value in raw]
