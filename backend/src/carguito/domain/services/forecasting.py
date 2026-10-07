from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ForecastPoint:
    month_offset: int
    baseline_net_worth: Decimal
    optimized_net_worth: Decimal


@dataclass(frozen=True)
class SimulationInput:
    starting_net_worth: Decimal
    monthly_income: Decimal
    monthly_expenses: Decimal
    monthly_savings_override: Decimal | None = None
    discretionary_spending: Decimal | None = None
    annual_return_rate: float = 0.0
    months: int = 12


class ForecastingService:
    """Projects net worth forward under a baseline and an optimized scenario.

    Deliberately simple (compounding monthly cash flow) so the UI Forecast
    Simulator can call it interactively; more sophisticated modelling can be
    layered in later without changing the port.
    """

    def project(self, sim: SimulationInput) -> list[ForecastPoint]:
        monthly_rate = sim.annual_return_rate / 12.0

        baseline_cf = sim.monthly_income - sim.monthly_expenses
        optimized_expenses = (
            sim.discretionary_spending
            if sim.discretionary_spending is not None
            else sim.monthly_expenses
        )
        optimized_cf = (
            sim.monthly_savings_override
            if sim.monthly_savings_override is not None
            else (sim.monthly_income - optimized_expenses)
        )

        points: list[ForecastPoint] = []
        baseline = sim.starting_net_worth
        optimized = sim.starting_net_worth
        for month in range(1, sim.months + 1):
            baseline = self._step(baseline, baseline_cf, monthly_rate)
            optimized = self._step(optimized, optimized_cf, monthly_rate)
            points.append(
                ForecastPoint(
                    month_offset=month,
                    baseline_net_worth=baseline,
                    optimized_net_worth=optimized,
                )
            )
        return points

    @staticmethod
    def _step(net_worth: Decimal, cash_flow: Decimal, monthly_rate: float) -> Decimal:
        grown = net_worth * (Decimal(1) + Decimal(str(monthly_rate)))
        return (grown + cash_flow).quantize(Decimal("0.01"))
