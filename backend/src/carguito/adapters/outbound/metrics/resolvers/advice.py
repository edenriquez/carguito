"""``financial_advice`` -- the advisor's principles as a computed metric.

The advice is a Python function over a *series*, not a SUM, so it is a resolver
rather than a compiled aggregation: "is this month's income 30% above its own
trailing baseline" has no expression in the measure x dimension x filter
grammar.

The series itself is **not** hand-rolled here. It is the ``monthly_cash_flow``
metric, executed through the same engine the widget uses, which is the whole
point of the measure-level ``default_filters``: a second SUM written in this
file would be a second place that has to remember transfers and excluded rows,
and per docs/redesign-plan.md §1 one of the two always forgets.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from .....application.dtos.metrics import (
    DEFAULT_CURRENCY,
    MetricMeta,
    MetricQuery,
    MetricResult,
    Period,
    ResolverContext,
    money,
)
from .....application.ports.outbound.metrics import MetricEngine
from .....domain.metrics.catalog import MONTHLY_CASH_FLOW
from .....domain.services.advisor import (
    MIN_MONTHS_OF_HISTORY,
    Advice,
    MonthlyFlow,
    evaluate_principles,
)


class FinancialAdviceResolver:
    """Implements the :class:`MetricResolver` port for ``financial_advice``."""

    metric_id = "financial_advice"

    def __init__(self, engine: MetricEngine) -> None:
        self._engine = engine

    def resolve(
        self, user_id: UUID, query: MetricQuery, ctx: ResolverContext
    ) -> MetricResult:
        series, source_count = self._series(user_id, query)
        advices = evaluate_principles(series)

        return MetricResult(
            metric_id=ctx.spec.id,
            shape=ctx.spec.shape,
            unit=ctx.spec.unit,
            # No headline number: the answer is a sentence. A `0` here would be
            # read as an amount by every generic renderer that meets it.
            value=None,
            rows=[_row(a) for a in advices],
            meta=MetricMeta(
                currency=DEFAULT_CURRENCY,
                # Short history is a *partial* answer, not an empty one: the
                # principle still renders, the frame says what is missing.
                partial=len(series) < MIN_MONTHS_OF_HISTORY,
                source_txn_count=source_count,
            ),
        )

    # --- the series ------------------------------------------------------
    def _series(
        self, user_id: UUID, query: MetricQuery
    ) -> tuple[list[MonthlyFlow], int | None]:
        """Monthly income/expense for the user, oldest first.

        Deliberately unbounded in time rather than scoped to ``query.period``:
        the metric declares ``ignores_period`` because advice is a claim about
        the user's latest month against its own trailing history, and narrowing
        that to whatever the dashboard's period selector says would silently
        redefine both "latest" and "baseline".
        """
        result = self._engine.execute(
            user_id,
            MONTHLY_CASH_FLOW,
            MetricQuery(
                key=query.key,
                metric=MONTHLY_CASH_FLOW.id,
                grain="month",
                period=Period(),
            ),
        )
        # The engine orders a series by its grain axis ascending, so "most
        # recent last" is already true; sorting again keeps that a property of
        # this file rather than an assumption about another one.
        rows = sorted(result.rows, key=lambda r: str(r.get("month") or ""))
        series = [
            MonthlyFlow(
                month=str(row.get("month")),
                income=_decimal(row.get("income_amount")),
                expense=_decimal(row.get("expense_amount")),
            )
            for row in rows
            if row.get("month")
        ]
        return series, result.meta.source_txn_count


def _row(advice: Advice) -> dict[str, Any]:
    return {
        "principle_id": advice.principle_id,
        "phrase": advice.phrase,
        "active": advice.active,
        "reason": advice.reason,
        "suggested_amount": money(advice.suggested_amount),
        "month": advice.month,
        "months_of_history": advice.months_of_history,
    }


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)
