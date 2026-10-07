from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class CategorySpend:
    category_id: str | None
    category_name: str
    amount: Decimal
    percentage: float


@dataclass(frozen=True)
class MonthlyPoint:
    month: str  # YYYY-MM
    income: Decimal
    expense: Decimal


@dataclass(frozen=True)
class RecurringCharge:
    """One occurrence of a recurring series: the evidence behind the rhythm."""

    date: str  # ISO
    amount: Decimal


@dataclass(frozen=True)
class RecurringItem:
    #: Stable grouping identity from RecurrenceService — survives a new charge,
    #: unlike last_date. What a pin must be stored as.
    key: str
    label: str
    occurrences: int
    frequency: str  # weekly | biweekly | monthly | bimonthly | semiannual | yearly
    typical_amount: Decimal
    monthly_equivalent: Decimal
    amount_stable: bool
    last_date: str  # ISO
    next_expected: str  # ISO
    category_id: str | None
    #: Every charge, oldest first — what the calendar view is drawn from.
    charges: tuple[RecurringCharge, ...] = ()


@dataclass(frozen=True)
class SpendingSummary:
    total_income: Decimal
    total_expense: Decimal
    top_category: str | None
    by_category: list[CategorySpend] = field(default_factory=list)
    monthly: list[MonthlyPoint] = field(default_factory=list)
