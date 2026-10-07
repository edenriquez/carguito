"""The shape of a saved lens: how often, how regularly, over how long.

Pure domain, same register as ``domain/services/advisor.py``: it receives a
per-day series and returns a description of the habit. No repository, no cube,
no clock -- which is what lets the arithmetic be tested as arithmetic instead of
as a fixture of transactions.

The rule this file inherits from the advisor: **it must be able to say it does
not know.** A frequency computed over three movements is noise wearing a unit,
and a "cada 1.8 días" derived from two dates is a coincidence. Every field that
cannot be honestly stated comes back ``None``, and the frame above says what is
missing rather than printing a confident number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

#: Below this many movements, "how often" is not a rate -- it is a coincidence
#: with a denominator. Three top-ups in a week reads as 3/week and predicts
#: nothing.
MIN_MOVEMENTS = 6
#: And below this many months, a per-month figure is one month restated. The
#: user is told to come back, not shown a number that will move by 300% on the
#: next statement.
MIN_MONTHS = 2

#: Average days per month over a 4-year cycle. Used to turn a span into months
#: without pretending every month is 30 days.
_DAYS_PER_MONTH = Decimal("30.4375")
_DAYS_PER_WEEK = Decimal(7)


@dataclass(frozen=True)
class ActiveDay:
    """One day the set had movement on, and how much."""

    day: date
    total: Decimal
    count: int


@dataclass(frozen=True)
class Rhythm:
    """How a set behaves over time. ``None`` wherever it cannot be stated.

    ``per_week`` and ``per_month`` are the same fact in two units; the client
    picks whichever reads honestly (a sub-weekly habit as ``3.8/sem``, a
    monthly one as ``1.1/mes``) rather than being handed one and forced to
    divide.
    """

    count: int
    days_covered: int
    months_covered: Decimal | None
    per_week: Decimal | None
    per_month: Decimal | None
    #: Typical gap between movements. The measure that actually answers "should
    #: I do this weekly instead" -- a mean gap is dragged around by one holiday.
    median_days_between: Decimal | None
    #: True when the set is too small or too short to describe honestly. The
    #: totals above it are still exact; only the rates are withheld.
    partial: bool


def describe_rhythm(days: Sequence[ActiveDay]) -> Rhythm:
    """Turn the active days of a set into its rhythm.

    ``days`` need not be sorted; it is sorted here so callers cannot make the
    gap arithmetic depend on the order a query happened to return.
    """
    ordered = sorted(days, key=lambda d: d.day)
    count = sum(d.count for d in ordered)

    if not ordered:
        return Rhythm(
            count=0,
            days_covered=0,
            months_covered=None,
            per_week=None,
            per_month=None,
            median_days_between=None,
            partial=True,
        )

    # Inclusive span: a set whose only movements are on the 1st and the 8th
    # covers 8 days, not 7. Exclusive would make a single-day set span zero and
    # every rate an infinity.
    span_days = (ordered[-1].day - ordered[0].day).days + 1
    months = _round(Decimal(span_days) / _DAYS_PER_MONTH)

    partial = count < MIN_MOVEMENTS or months < MIN_MONTHS
    if partial:
        # The rates are withheld, not zeroed. `days_covered` and `count` are
        # facts and survive; a `0.0/sem` would be a claim the data cannot make.
        return Rhythm(
            count=count,
            days_covered=span_days,
            months_covered=months,
            per_week=None,
            per_month=None,
            median_days_between=_median_gap(ordered),
            partial=True,
        )

    span = Decimal(span_days)
    return Rhythm(
        count=count,
        days_covered=span_days,
        months_covered=months,
        per_week=_round(Decimal(count) * _DAYS_PER_WEEK / span),
        per_month=_round(Decimal(count) * _DAYS_PER_MONTH / span),
        median_days_between=_median_gap(ordered),
        partial=False,
    )


def _median_gap(ordered: Sequence[ActiveDay]) -> Decimal | None:
    """Median days between consecutive movements, or ``None`` under two.

    Days with more than one movement contribute a zero-day gap for each extra
    one: four top-ups on the same afternoon really are zero days apart, and
    dropping those would report the habit as slower than it is.
    """
    gaps: list[Decimal] = []
    previous: date | None = None
    for entry in ordered:
        if previous is not None:
            gaps.append(Decimal((entry.day - previous).days))
        gaps.extend(Decimal(0) for _ in range(entry.count - 1))
        previous = entry.day

    if not gaps:
        return None
    return _round(median(gaps))


def median(values: Sequence[Decimal]) -> Decimal:
    """The middle value; the mean of the middle two when there is no middle.

    Written here rather than taken from ``statistics`` so it stays in Decimal
    end to end -- ``statistics.median`` returns a float for an even-length list
    and a float peso is how a total stops adding up.
    """
    if not values:
        raise ValueError("median of no values")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _round(value: Decimal) -> Decimal:
    """Two decimals. A rate is a reading, not an accounting figure."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
