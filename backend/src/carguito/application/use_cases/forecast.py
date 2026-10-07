from __future__ import annotations

import statistics
from decimal import Decimal
from uuid import UUID

from ...domain.services.forecasting import ForecastingService, ForecastPoint, SimulationInput
from ..ports.outbound import CubeReader


class GetForecastUseCase:
    """Builds a default forecast from the user's recent cash-flow history."""

    def __init__(self, cube: CubeReader, service: ForecastingService | None = None) -> None:
        self._cube = cube
        self._service = service or ForecastingService()

    def execute(self, *, user_id: UUID, months: int = 12) -> list[ForecastPoint]:
        series = self._cube.monthly_series(user_id, months=6)
        avg_income = _avg((p.income for p in series))
        avg_expense = _avg((p.expense for p in series))
        starting = _sum(p.income - p.expense for p in series)
        sim = SimulationInput(
            starting_net_worth=starting,
            monthly_income=avg_income,
            monthly_expenses=avg_expense,
            months=months,
        )
        return self._service.project(sim)


class SimulateForecastUseCase:
    """Runs the interactive Forecast Simulator with user-supplied sliders."""

    def __init__(self, service: ForecastingService | None = None) -> None:
        self._service = service or ForecastingService()

    def execute(self, sim: SimulationInput) -> list[ForecastPoint]:
        return self._service.project(sim)


def _avg(values) -> Decimal:
    vals = [float(v) for v in values]
    return Decimal(str(statistics.mean(vals))).quantize(Decimal("0.01")) if vals else Decimal("0")


def _sum(values) -> Decimal:
    total = Decimal("0")
    for v in values:
        total += Decimal(str(v))
    return total.quantize(Decimal("0.01"))
