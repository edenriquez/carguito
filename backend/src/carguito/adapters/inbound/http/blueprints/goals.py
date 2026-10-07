from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, jsonify, request

from ..auth import current_user_id, get_container
from ..serialization import goal_json

goals_bp = Blueprint("goals", __name__, url_prefix="/api/goals")


@goals_bp.get("")
def list_goals():
    user_id = current_user_id()
    goals = get_container().manage_goals.list(user_id=user_id)
    return jsonify(items=[goal_json(g) for g in goals])


@goals_bp.post("")
def create_goal():
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    if not body.get("name") or "target_amount" not in body:
        return jsonify(error="name and target_amount are required"), 400

    goal = get_container().manage_goals.create(
        user_id=user_id,
        name=body["name"],
        target_amount=Decimal(str(body["target_amount"])),
        current_amount=Decimal(str(body.get("current_amount", 0))),
        target_date=date.fromisoformat(body["target_date"]) if body.get("target_date") else None,
    )
    return jsonify(goal_json(goal)), 201


@goals_bp.patch("/<goal_id>")
def update_goal(goal_id: str):
    current_user_id()
    body = request.get_json(silent=True) or {}
    if "current_amount" not in body:
        return jsonify(error="current_amount is required"), 400
    goal = get_container().manage_goals.update_progress(
        goal_id=UUID(goal_id), current_amount=Decimal(str(body["current_amount"]))
    )
    if goal is None:
        return jsonify(error="Goal not found"), 404
    return jsonify(goal_json(goal))


@goals_bp.delete("/<goal_id>")
def delete_goal(goal_id: str):
    current_user_id()
    get_container().manage_goals.delete(goal_id=UUID(goal_id))
    return "", 204
