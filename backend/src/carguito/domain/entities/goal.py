from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass(slots=True)
class Goal:
    user_id: UUID
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0")
    target_date: date | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()

    @property
    def progress(self) -> float:
        """Completion ratio in [0, 1]."""
        if self.target_amount <= 0:
            return 0.0
        return min(1.0, float(self.current_amount / self.target_amount))
