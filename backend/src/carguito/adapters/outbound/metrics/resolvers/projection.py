"""The computed half of the registry: a metric that is a Python function.

``investment_projection`` is a function of numbers the user typed, not of the
fact table -- no statement parser reads a balance and no statement carries a
rate. It exists to prove the envelope is bimodal: the client posts it to the
same endpoint, keyed the same way, and cannot tell it apart from a metric that
compiled to SQL. If it ever becomes derivable (B8: accounts, balances, rates),
it can move behind the engine without a client change.

The maths is not reimplemented; ``domain/services/forecasting.py`` already owns
it. This adapter only maps params onto :class:`SimulationInput`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from .....application.dtos.metrics import (
    DEFAULT_CURRENCY,
    MetricMeta,
    MetricQuery,
    MetricResult,
    ResolverContext,
    money,
)
from .....domain.services.forecasting import ForecastingService, SimulationInput


class InvestmentProjectionResolver:
    """Implements the :class:`MetricResolver` port for ``investment_projection``."""

    metric_id = "investment_projection"

    def __init__(self, forecasting: ForecastingService | None = None) -> None:
        self._forecasting = forecasting or ForecastingService()

    def resolve(
        self, user_id: UUID, query: MetricQuery, ctx: ResolverContext
    ) -> MetricResult:
        params = ctx.spec.coerce_params(query.params)

        # ForecastingService models a whole net-worth scenario; a projection is
        # the degenerate case of it -- contributions are the only inflow and
        # there are no outflows, so baseline and optimized coincide and only
        # the baseline series is reported.
        points = self._forecasting.project(
            SimulationInput(
                starting_net_worth=Decimal(params["starting_balance"]),
                monthly_income=Decimal(params["monthly_contribution"]),
                monthly_expenses=Decimal(0),
                annual_return_rate=float(params["annual_rate"]),
                months=int(params["months"]),
            )
        )

        rows = [
            {"month_offset": p.month_offset, "value": money(p.baseline_net_worth)}
            for p in points
        ]
        return MetricResult(
            metric_id=ctx.spec.id,
            shape=ctx.spec.shape,
            unit=ctx.spec.unit,
            value=rows[-1]["value"] if rows else None,
            rows=rows,
            meta=MetricMeta(
                currency=DEFAULT_CURRENCY,
                # Not derived from transactions at all -- reporting 0 here would
                # read as "no data found" rather than "not that kind of metric".
                source_txn_count=None,
            ),
        )
