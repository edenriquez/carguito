from __future__ import annotations

from datetime import date
from uuid import UUID

from ..dtos.analytics import SpendingSummary
from ..ports.outbound import CubeReader


class GetSpendingSummaryUseCase:
    """Reads aggregated spending from the analytics cube."""

    def __init__(self, cube: CubeReader) -> None:
        self._cube = cube

    def execute(
        self, *, user_id: UUID, start: date | None = None, end: date | None = None
    ) -> SpendingSummary:
        return self._cube.spending_summary(user_id, start, end)
