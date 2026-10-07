from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.entities import Goal
from ..ports.outbound import GoalRepository


class ManageGoalsUseCase:
    """CRUD for savings goals (Metas)."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    def list(self, *, user_id: UUID) -> list[Goal]:
        return self._goals.list_for_user(user_id)

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        target_amount: Decimal,
        current_amount: Decimal = Decimal("0"),
        target_date: date | None = None,
    ) -> Goal:
        goal = Goal(
            user_id=user_id,
            name=name,
            target_amount=target_amount,
            current_amount=current_amount,
            target_date=target_date,
        )
        self._goals.add(goal)
        return goal

    def update_progress(self, *, goal_id: UUID, current_amount: Decimal) -> Goal | None:
        goal = self._goals.get(goal_id)
        if goal is None:
            return None
        goal.current_amount = current_amount
        self._goals.update(goal)
        return goal

    def delete(self, *, goal_id: UUID) -> None:
        self._goals.delete(goal_id)
