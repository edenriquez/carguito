"""The advisor's principle engine (docs/advisor-principles.md).

Pure domain: it receives a monthly income/expense series and returns advice.
No repository, no cube, no clock -- same shape as
``domain/services/categorization.py``, which is what lets the trigger matrix be
tested as arithmetic instead of as a fixture of transactions.

The rule the corpus imposes on this file: **precision over recall**. One wrong
"urgente" and the feature is muted forever, so every branch that cannot state
the user's own numbers returns the dormant principle rather than a guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

#: P1 requires four months before it will speak at all: a "trailing average"
#: over two months is the user's last paycheck wearing a statistics costume.
MIN_MONTHS_OF_HISTORY = 4
#: The baseline window, excluding the month being judged. Six months is long
#: enough to absorb one aguinaldo and short enough to track a real raise.
BASELINE_MONTHS = 6
#: A month has to clear the average by this much to be an outlier rather than
#: noise...
INCOME_TRIGGER_RATIO = Decimal("1.30")
#: ...and the excess has to be material. 30% over a tiny base is a rounding
#: error with a percentage sign.
MIN_EXCESS = Decimal(3000)
#: Anti-trigger: expenses that rose this much against their own baseline mean
#: lifestyle inflation is already happening, so the copy sharpens instead of
#: congratulating.
EXPENSE_INFLATION_RATIO = Decimal("1.20")

P1_ID = "P1"
#: Verbatim from the corpus. The one accented, punctuated string in the
#: product: it is the principle, not UI copy, and rewording it in transit is
#: how a proverb turns into a slogan.
P1_PHRASE = "«Si te va muy bien, ahorra… urgentemente; un arbol nunca llega al cielo.»"
#: The dormant body: the mechanism in one line, no urgency, always true.
P1_MECHANISM = (
    "Los meses excepcionales se sienten como un nuevo normal y casi nunca lo son. "
    "Cuando tu ingreso mensual supere tu promedio, aqui te decimos cuanto apartar."
)


@dataclass(frozen=True)
class MonthlyFlow:
    """One month of the ledger. ``month`` is a ``YYYY-MM`` bucket key."""

    month: str
    income: Decimal
    expense: Decimal


@dataclass(frozen=True)
class Advice:
    """One principle evaluated against one user's data.

    ``active`` is the only field the UI keys urgency off. A dormant principle is
    still returned, with the same phrase and a reason -- it is true always and
    urgent only when the data says so.
    """

    principle_id: str
    phrase: str
    active: bool
    reason: str
    #: The excess over baseline: the "cheap money" the mechanism identifies, not
    #: a generic percentage. ``None`` whenever the principle is dormant.
    suggested_amount: Decimal | None
    months_of_history: int
    #: The month the advice is about, so the product hook can deep-link to it.
    month: str | None = None


def evaluate_principles(series: Sequence[MonthlyFlow]) -> list[Advice]:
    """Every principle in the corpus, evaluated. Today: P1."""
    return [evaluate_p1(series)]


def evaluate_p1(series: Sequence[MonthlyFlow]) -> Advice:
    """P1 -- El arbol nunca llega al cielo (docs/advisor-principles.md).

    Fires when the latest month's income clears its trailing baseline by both a
    ratio *and* an absolute amount. Both conditions are load-bearing: the ratio
    alone fires on a base of nothing, the absolute alone fires on every good
    month of a large income.
    """
    months = len(series)
    if months < MIN_MONTHS_OF_HISTORY:
        return _dormant(months, series[-1].month if series else None)

    latest = series[-1]
    history = series[-(BASELINE_MONTHS + 1) : -1]
    baseline = _mean(f.income for f in history)

    # A zero baseline makes the ratio meaningless (everything is infinitely
    # above nothing), so the principle stays quiet rather than shouting at the
    # user's first month of recorded income.
    if baseline <= 0:
        return _dormant(months, latest.month)

    excess = latest.income - baseline
    if latest.income < INCOME_TRIGGER_RATIO * baseline or excess < MIN_EXCESS:
        return _dormant(months, latest.month)

    expense_baseline = _mean(f.expense for f in history)
    inflating = (
        expense_baseline > 0
        and latest.expense >= EXPENSE_INFLATION_RATIO * expense_baseline
    )

    return Advice(
        principle_id=P1_ID,
        phrase=P1_PHRASE,
        active=True,
        reason=_active_reason(latest, baseline, excess, expense_baseline, inflating),
        suggested_amount=_cents(excess),
        months_of_history=months,
        month=latest.month,
    )


# --- copy -----------------------------------------------------------------
def _active_reason(
    latest: MonthlyFlow,
    baseline: Decimal,
    excess: Decimal,
    expense_baseline: Decimal,
    inflating: bool,
) -> str:
    above = _percent(excess / baseline)
    head = (
        f"Este mes ingresaste {_amount(latest.income)}, {above}% arriba de tu "
        f"promedio de {_amount(baseline)}."
    )
    if not inflating:
        return (
            f"{head} Los meses asi no se repiten: aparta la diferencia "
            f"({_amount(excess)}) antes de que el gasto se acomode."
        )
    # The anti-trigger case. Congratulating here would be wrong: the spending
    # has *already* adjusted upward, so the sentence names that instead.
    rise = _percent((latest.expense - expense_baseline) / expense_baseline)
    return (
        f"{head} Tu gasto tambien subio {rise}%, de {_amount(expense_baseline)} a "
        f"{_amount(latest.expense)}: el acomodo ya empezo. Aparta "
        f"{_amount(excess)} ahora, antes de que se lo lleve el mes que viene."
    )


def _dormant(months: int, month: str | None) -> Advice:
    return Advice(
        principle_id=P1_ID,
        phrase=P1_PHRASE,
        active=False,
        reason=P1_MECHANISM,
        suggested_amount=None,
        months_of_history=months,
        month=month,
    )


# --- arithmetic -----------------------------------------------------------
def _mean(values) -> Decimal:
    items = list(values)
    if not items:
        return Decimal(0)
    return sum(items, Decimal(0)) / Decimal(len(items))


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _percent(ratio: Decimal) -> str:
    return str(int((ratio * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def _amount(value: Decimal) -> str:
    """A plain grouped figure -- no currency symbol.

    The reason is a sentence the client renders as-is; the *amounts* inside it
    are the user's own numbers and the client owns currency formatting, so the
    backend never bakes a peso sign into text it cannot re-format.
    """
    return f"{value.quantize(Decimal(1), rounding=ROUND_HALF_UP):,}"
