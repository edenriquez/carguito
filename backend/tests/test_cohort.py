"""The rhythm arithmetic, as arithmetic (docs/redesign-plan.md §9).

Same shape as ``test_advisor.py``: no fixtures of transactions, no cube, no
HTTP. A rhythm is a function of a list of dates and counts, and the point of
these tests is that it stays one.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from carguito.domain.services.cohort import (
    MIN_MONTHS,
    MIN_MOVEMENTS,
    ActiveDay,
    describe_rhythm,
    median,
)


def day(y: int, m: int, d: int, total: str = "15", count: int = 1) -> ActiveDay:
    return ActiveDay(day=date(y, m, d), total=Decimal(total), count=count)


# --- median ---------------------------------------------------------------
def test_median_of_odd_and_even_lengths():
    assert median([Decimal(3), Decimal(1), Decimal(2)]) == Decimal(2)
    assert median([Decimal(1), Decimal(2), Decimal(3), Decimal(4)]) == Decimal("2.5")


def test_median_stays_in_decimal():
    # A float peso is how a total stops adding up. `statistics.median` returns
    # one for an even-length list, which is why this function exists.
    result = median([Decimal("0.10"), Decimal("0.20")])
    assert isinstance(result, Decimal)
    assert result == Decimal("0.15")


def test_median_of_nothing_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        median([])


# --- empty and tiny sets --------------------------------------------------
def test_no_movements_states_nothing():
    r = describe_rhythm([])
    assert r.count == 0
    assert r.partial is True
    # Not 0.0/week. The set is empty; it has no rate, and a zero would be read
    # as "you never do this" rather than "there is nothing here".
    assert r.per_week is None
    assert r.per_month is None
    assert r.median_days_between is None


def test_a_single_movement_has_no_gap():
    r = describe_rhythm([day(2024, 1, 5)])
    assert r.count == 1
    assert r.days_covered == 1  # inclusive span, never zero
    assert r.median_days_between is None
    assert r.partial is True


def test_too_few_movements_withholds_the_rate_but_keeps_the_facts():
    # Five movements over four months: long enough, not numerous enough.
    days = [day(2024, 1, 1), day(2024, 2, 1), day(2024, 3, 1), day(2024, 4, 1), day(2024, 4, 2)]
    assert len(days) < MIN_MOVEMENTS
    r = describe_rhythm(days)
    assert r.partial is True
    assert r.per_week is None
    # The counts are exact and survive the partial verdict.
    assert r.count == 5
    assert r.days_covered == 93


def test_too_short_a_history_withholds_the_rate():
    # Eight movements inside one month: numerous enough, too short.
    days = [day(2024, 1, d) for d in range(1, 9)]
    r = describe_rhythm(days)
    assert r.count >= MIN_MOVEMENTS
    assert r.months_covered < MIN_MONTHS
    assert r.partial is True
    assert r.per_month is None


# --- the honest cases -----------------------------------------------------
def test_weekly_habit_reads_as_one_per_week():
    # Ten movements, one every 7 days: span 64 days inclusive.
    days = [ActiveDay(date.fromordinal(date(2024, 1, 1).toordinal() + 7 * i), Decimal(15), 1)
            for i in range(10)]
    r = describe_rhythm(days)
    assert r.partial is False
    assert r.median_days_between == Decimal(7)
    # 10 movements / 64 days * 7 = 1.09
    assert r.per_week == Decimal("1.09")


def test_several_movements_on_one_day_are_zero_days_apart():
    # Four top-ups on the same afternoon really are zero days apart. Counting
    # only distinct days would report the habit as four times slower.
    days = [day(2024, 1, 1, count=4), day(2024, 3, 1, count=4)]
    r = describe_rhythm(days)
    assert r.count == 8
    # Gaps: 0,0,0 (Jan) then 60 then 0,0,0 (Mar) -> median 0.
    assert r.median_days_between == Decimal(0)


def test_count_reads_the_count_not_the_number_of_days():
    r = describe_rhythm([day(2024, 1, 1, count=3), day(2024, 4, 1, count=3)])
    assert r.count == 6
    assert r.days_covered == 92


def test_order_of_input_does_not_change_the_answer():
    days = [day(2024, 3, 1), day(2024, 1, 1), day(2024, 2, 1),
            day(2024, 1, 15), day(2024, 2, 15), day(2024, 3, 15)]
    forward = describe_rhythm(days)
    backward = describe_rhythm(list(reversed(days)))
    assert forward == backward
    assert forward.partial is False


def test_span_is_inclusive_so_a_rate_is_never_infinite():
    # Two movements on the same day: an exclusive span would be 0 days and
    # every rate a division by zero.
    r = describe_rhythm([day(2024, 1, 1, count=2)])
    assert r.days_covered == 1
    assert r.per_week is None  # partial, but by the count rule -- not a crash


def test_per_week_and_per_month_describe_the_same_fact():
    days = [ActiveDay(date.fromordinal(date(2024, 1, 1).toordinal() + 3 * i), Decimal(15), 1)
            for i in range(30)]
    r = describe_rhythm(days)
    assert r.partial is False
    # per_month / per_week must be the days-per-month / days-per-week ratio,
    # within the rounding both were quantized to.
    ratio = r.per_month / r.per_week
    assert abs(ratio - Decimal("30.4375") / Decimal(7)) < Decimal("0.01")
