"""The P1 trigger matrix (docs/advisor-principles.md).

Pure arithmetic against the domain service: no app, no cube, no HTTP. The
matrix is the point -- P1's two conditions are an AND, and a test that only
covers the firing case cannot tell an AND from an OR.
"""

from __future__ import annotations

from decimal import Decimal

from carguito.domain.services.advisor import (
    P1_MECHANISM,
    P1_PHRASE,
    MonthlyFlow,
    evaluate_p1,
    evaluate_principles,
)


def series(*months, expense=Decimal(8000)):
    """`months` is (income[, expense]) per month, oldest first."""
    out = []
    for index, item in enumerate(months, start=1):
        income, exp = item if isinstance(item, tuple) else (item, expense)
        out.append(
            MonthlyFlow(
                month=f"2024-{index:02d}",
                income=Decimal(str(income)),
                expense=Decimal(str(exp)),
            )
        )
    return out


def test_fires_when_income_clears_both_the_ratio_and_the_absolute_floor():
    advice = evaluate_p1(series(20000, 20000, 20000, 20000, 20000, 30000))

    assert advice.active is True
    assert advice.principle_id == "P1"
    assert advice.phrase == P1_PHRASE
    # The suggested amount is the excess over baseline -- the "cheap money" the
    # mechanism identifies -- not a generic percentage of income.
    assert advice.suggested_amount == Decimal("10000.00")
    assert advice.months_of_history == 6
    assert advice.month == "2024-06"
    # The reason carries the user's own numbers; the advisor never surfaces an
    # unexplained score.
    assert "30,000" in advice.reason
    assert "20,000" in advice.reason
    assert "50%" in advice.reason
    assert "aparta la diferencia" in advice.reason


def test_baseline_excludes_the_month_being_judged():
    # A latest month included in its own average would drag the baseline up and
    # under-report the excess.
    advice = evaluate_p1(series(10000, 10000, 10000, 10000, 40000))
    assert advice.active is True
    assert advice.suggested_amount == Decimal("30000.00")


def test_baseline_window_is_the_trailing_six_months_only():
    # The ancient 100k month must not inflate today's baseline.
    advice = evaluate_p1(
        series(100000, 10000, 10000, 10000, 10000, 10000, 10000, 20000)
    )
    assert advice.active is True
    assert advice.suggested_amount == Decimal("10000.00")


def test_dormant_under_the_ratio():
    # +20%: above average, but not an outlier month.
    advice = evaluate_p1(series(20000, 20000, 20000, 20000, 24000))

    assert advice.active is False
    assert advice.suggested_amount is None
    assert advice.reason == P1_MECHANISM
    # Dormant is not silent: the principle is true always and still renders.
    assert advice.phrase == P1_PHRASE


def test_dormant_under_the_absolute_floor():
    # +40% clears the ratio, but 2,000 pesos of excess is noise on a small base.
    advice = evaluate_p1(series(5000, 5000, 5000, 5000, 7000))

    assert advice.active is False
    assert advice.suggested_amount is None


def test_dormant_with_insufficient_history():
    advice = evaluate_p1(series(1000, 1000, 90000))

    assert advice.active is False
    assert advice.months_of_history == 3
    assert advice.suggested_amount is None


def test_dormant_when_the_baseline_is_zero():
    # Everything is infinitely above nothing; the ratio means nothing here.
    advice = evaluate_p1(series(0, 0, 0, 0, 50000))
    assert advice.active is False


def test_anti_trigger_sharpens_the_copy_when_expenses_rose_too():
    advice = evaluate_p1(
        series(
            (20000, 10000),
            (20000, 10000),
            (20000, 10000),
            (20000, 10000),
            (30000, 13000),
        )
    )

    assert advice.active is True
    assert advice.suggested_amount == Decimal("10000.00")
    # Lifestyle inflation is already happening, so the sentence names it
    # instead of congratulating.
    assert "el acomodo ya empezo" in advice.reason
    assert "30%" in advice.reason  # expenses 10,000 -> 13,000
    assert "aparta la diferencia" not in advice.reason


def test_expenses_below_the_inflation_threshold_keep_the_plain_copy():
    advice = evaluate_p1(
        series(
            (20000, 10000),
            (20000, 10000),
            (20000, 10000),
            (20000, 10000),
            (30000, 11000),
        )
    )
    assert "el acomodo ya empezo" not in advice.reason
    assert "aparta la diferencia" in advice.reason


def test_empty_history_is_dormant_rather_than_an_error():
    advice = evaluate_p1([])
    assert advice.active is False
    assert advice.months_of_history == 0
    assert advice.month is None


def test_evaluate_principles_returns_the_whole_corpus():
    advices = evaluate_principles(series(20000, 20000, 20000, 20000, 30000))
    assert [a.principle_id for a in advices] == ["P1"]
