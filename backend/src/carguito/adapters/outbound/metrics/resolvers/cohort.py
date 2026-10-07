"""``cohort_profile`` -- the reading of a saved lens over the ledger.

Like the advisor, this is a resolver rather than a compiled aggregation because
its headline fact has no expression in the measure x dimension x filter grammar:
"cada 1.8 dias" is a function of the *gaps between* rows, and SQL that groups
rows cannot see between them.

Also like the advisor, it does not write its own SUM. It executes
``cohort_activity`` and ``cohort_totals`` through the same engine the widgets
use, carrying the caller's filters through untouched, so "spend excludes
transfers and excluded rows" stays declared once in the vocabulary. Two round
trips inside one resolver is cheaper than two definitions of what spend is.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from .....application.dtos.metrics import (
    DEFAULT_CURRENCY,
    MetricMeta,
    MetricQuery,
    MetricResult,
    ResolverContext,
    money,
)
from .....application.ports.outbound.metrics import MetricEngine
from .....domain.metrics.catalog import COHORT_ACTIVITY, COHORT_TOTALS
from .....domain.services.cohort import ActiveDay, describe_rhythm


class CohortProfileResolver:
    """Implements the :class:`MetricResolver` port for ``cohort_profile``."""

    metric_id = "cohort_profile"

    def __init__(self, engine: MetricEngine) -> None:
        self._engine = engine

    def resolve(self, user_id: UUID, query: MetricQuery, ctx: ResolverContext) -> MetricResult:
        totals = self._engine.execute(user_id, COHORT_TOTALS, self._sub(query, COHORT_TOTALS))
        activity = self._engine.execute(
            user_id, COHORT_ACTIVITY, self._sub(query, COHORT_ACTIVITY, grain="day")
        )

        rhythm = describe_rhythm(_active_days(activity.rows))
        scalars = totals.rows[0] if totals.rows else {}
        count = rhythm.count

        # An empty set gets one row of nothings rather than no rows: the frame
        # has to be able to say "ningun movimiento cumple esta regla", and a
        # zero-row table is indistinguishable from a metric that failed.
        row: dict[str, Any] = {
            "count": count,
            "total": money(_dec(scalars.get("expense_amount"))) if count else None,
            # The arithmetic mean, computed here rather than asked of SQL: it is
            # total/count either way, and this is the one place both are known
            # to have come from the same query.
            "mean": money(_mean(_dec(scalars.get("expense_amount")), count)) if count else None,
            "median": money(_dec(scalars.get("expense_median"))) if count else None,
            "min": money(_dec(scalars.get("expense_min"))) if count else None,
            "max": money(_dec(scalars.get("expense_max"))) if count else None,
            "days_covered": rhythm.days_covered or None,
            "months_covered": _num(rhythm.months_covered),
            # These three are `None` whenever the set is too small or too short
            # to describe. That is the contract with the frame above: it renders
            # "Necesitas 2 meses. Llevas 1." instead of a rate that will move by
            # 300% on the next statement.
            "per_week": _num(rhythm.per_week),
            "per_month": _num(rhythm.per_month),
            "median_days_between": _num(rhythm.median_days_between),
        }

        return MetricResult(
            metric_id=ctx.spec.id,
            shape=ctx.spec.shape,
            unit=ctx.spec.unit,
            # No headline number: the row is a description, not a measure. A
            # value here would be picked up as an amount by every generic
            # renderer that meets it.
            value=None,
            rows=[row],
            meta=MetricMeta(
                currency=DEFAULT_CURRENCY,
                partial=rhythm.partial,
                source_txn_count=totals.meta.source_txn_count,
            ),
        )

    @staticmethod
    def _sub(query: MetricQuery, spec, grain: str | None = None) -> MetricQuery:
        """The caller's query, aimed at one of the two metrics we lean on.

        The filters travel through verbatim -- they *are* the workstation's
        rule, and a profile computed over a different set than the chart draws
        would be the exact disagreement this design exists to prevent. So does
        the period: unlike advice, a cohort reading is scoped to the window the
        user is looking at.
        """
        return MetricQuery(
            key=query.key,
            metric=spec.id,
            filters=dict(query.filters),
            grain=grain,
            period=query.period,
        )


def _active_days(rows: list[dict[str, Any]]) -> list[ActiveDay]:
    """Day-grain rows -> the domain's view of them.

    Rows without a parseable day are dropped rather than defaulted: a movement
    on an unknown date cannot contribute to a gap, and inventing one would bend
    the rhythm toward whatever default was chosen.
    """
    days: list[ActiveDay] = []
    for row in rows:
        parsed = _day(row.get("day"))
        if parsed is None:
            continue
        days.append(
            ActiveDay(
                day=parsed,
                total=_dec(row.get("expense_amount")),
                count=int(_dec(row.get("tx_count"))),
            )
        )
    return days


def _day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _mean(total: Decimal, count: int) -> Decimal | None:
    return total / count if count else None


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)


def _num(value: Decimal | None) -> str | None:
    """Decimals leave as strings, like every other figure in the envelope.

    A rate is not money, but it is still a Decimal, and the reason money travels
    as a string (JSON's float will not carry it back unchanged) applies to a
    median gap of 1.5 days just as much.
    """
    return None if value is None else str(value)
