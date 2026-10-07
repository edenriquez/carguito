"""Transport shapes for the generic metric endpoint.

Money is serialised as a **string**, never a float (docs/redesign-plan.md §6).
``0.1 + 0.2`` is a rounding error the moment it reaches JSON, and a peso figure
that renders as ``4199.999999999999`` is a bug report. Decimals travel as
strings and the client formats them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ...domain.metrics.spec import MetricSpec

#: Aggregates are scoped to one currency; summing MXN and USD yields a number
#: denominated in nothing.
DEFAULT_CURRENCY = "MXN"

_CENTS = Decimal("0.01")


def money(value: Decimal | float | str | None) -> str | None:
    """Format a monetary amount for transport: fixed 2dp, as a string."""
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(_CENTS))


@dataclass(frozen=True)
class Period:
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class MetricQuery:
    """One widget's ask. ``key`` is the client's correlation id for the batch."""

    key: str
    metric: str
    dimensions: tuple[str, ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)
    grain: str | None = None
    period: Period = field(default_factory=Period)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricMeta:
    """Caveats that travel with the numbers.

    ``overlapping`` matters as soon as tags become a dimension (B6): a
    transaction with three tags lands in three rows and the parts no longer sum
    to the whole. Without the flag the client ships a pie chart totalling 240%.
    """

    currency: str | None = DEFAULT_CURRENCY
    overlapping: bool = False
    partial: bool = False
    source_txn_count: int | None = None


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    shape: str
    unit: str
    #: Headline figure, as a string. ``None`` when the shape has no single
    #: number (a two-measure series) or when there is no data -- never ``0``,
    #: because a zero is a claim about someone's finances and absence isn't.
    value: str | None
    rows: list[dict[str, Any]] = field(default_factory=list)
    meta: MetricMeta = field(default_factory=MetricMeta)


@dataclass(frozen=True)
class MetricError:
    """A single query's failure. Never raised past the batch boundary."""

    metric_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class MetricBatchResult:
    """Results keyed by the client's widget key. Values are result *or* error."""

    results: dict[str, MetricResult | MetricError] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolverContext:
    """What a computed metric's resolver gets besides the query itself."""

    spec: MetricSpec
