"""Recurring-charge detection: subscriptions, fixed bills, payroll deductions.

Every rule here is explainable, because every surfaced series makes a claim
about the user's future money ("Netflix vuelve a cobrar el día 5"). Precision
over recall — the same rule as the advisor and anomaly detection: one wrong
"recurring" and the tab reads as noise.

The gates, in order:
- **Grouping** is by normalized description with digit-heavy tokens stripped,
  so "OXXO SUC 4412" and "OXXO SUC 8891" collapse into one series and a folio
  number can't split a subscription into singletons.
- **A name the user typed on two or more charges is stronger than the bank
  text.** SPEI strings bury the month in the body ("SECUNDARIA JULIO"); the
  heuristic then splits "Colegiatura Demian" into one-charge groups. If the
  user already said they are the same thing, that is the series.
- **Three occurrences minimum.** Two is a coincidence.
- **Known Mexican utilities** (CFE) collapse to one identity even when the
  product line changes (SUM SERV → CONTIGO). CFE residential is bimonthly.
- **Cadence must be regular**: the *median* interval (robust to one late
  charge) classifies the frequency, and most gaps must sit near it. A
  merchant you merely visit often has no rhythm and is not a subscription.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from ..entities.transaction import Transaction
from ..value_objects.enums import TxType
from .aliases import AliasService
from .categorization import normalize

#: median-interval windows, in days, per frequency. Gaps between windows are
#: deliberate: a 22-day cadence is not "biweekly-ish", it is not a cadence.
_FREQUENCY_WINDOWS: list[tuple[str, float, float]] = [
    ("weekly", 5, 9),
    ("biweekly", 12, 18),
    ("monthly", 26, 35),
    # 6–8 weeks: a dentist, a bimestral utility that landed early.
    # Gap below 42 is deliberate — 40 days is still not monthly.
    ("bimonthly", 42, 80),
    # ~6 months: a policy, a predial installment. The gap under 160 is
    # deliberate — 90 days is quarterly, not semestral.
    ("semiannual", 160, 200),
    ("yearly", 350, 380),
]

_DIGIT = re.compile(r"\d")

#: Date-shaped substrings, removed BEFORE normalization. The digit-heavy strip
#: below kills "07" and "2026" on its own, but a "07-may-2026" prefix leaves
#: the month name behind as an innocent 3-letter token — and then two charges
#: of the same subscription key as "may …" vs "abr …" and split. Only month
#: names inside a date *shape* go: a merchant legitimately named "MAYO" keeps
#: its identity.
_MONTHS = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto"
    "|septiembre|setiembre|octubre|noviembre|diciembre"
    "|ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic"
)
_DATE_SHAPES = re.compile(
    rf"\b\d{{1,2}}[-/. ]?(?:{_MONTHS})[a-z]*[-/. ]?\d{{2,4}}\b"  # 07-may-2026
    rf"|\b(?:{_MONTHS})[-/. ]?\d{{1,2}}[-/. ]?\d{{2,4}}\b"  # may-07-2026
    r"|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"  # 07/05/2026
    r"|\b\d{4}-\d{2}-\d{2}\b",  # 2026-05-07
    re.IGNORECASE,
)


def series_key(description: str) -> str:
    """Grouping key: normalized text minus date shapes and digit-heavy tokens.

    Dates, folios, branch and card fragments vary per charge; the words are
    the identity. Same heuristic the frontend uses to suggest match labels,
    so what the user sees grouped is what a taught label would match.
    """
    without_dates = _DATE_SHAPES.sub(" ", description)
    words = []
    for token in normalize(without_dates).split(" "):
        digits = len(_DIGIT.findall(token))
        if len(token) >= 2 and digits <= len(token) / 2:
            words.append(token)
    return " ".join(words)


#: Bank product lines change; the utility does not. Any series whose words
#: include one of these tokens is that utility, not a new merchant.
_KNOWN_UTILITIES = {"cfe": "cfe"}

#: Charges below this fraction of the group's median are fees or adjustments,
#: not the bill — they must not break the cadence (CFE CONTIGO $18 next to
#: a $2,000 recibo).
_MICRO_CHARGE_FRACTION = 0.15


def _one_per_day(txs: list[Transaction]) -> list[Transaction]:
    """Keep one charge per calendar day — the larger amount wins."""
    by_day: dict[date, Transaction] = {}
    for t in txs:
        prev = by_day.get(t.tx_date)
        if prev is None or abs(float(t.amount)) > abs(float(prev.amount)):
            by_day[t.tx_date] = t
    return [by_day[d] for d in sorted(by_day)]


def known_utility_key(description: str) -> str | None:
    """Canonical key for a known utility, or None to keep the heuristic."""
    tokens = set(series_key(description).split())
    for token, key in _KNOWN_UTILITIES.items():
        if token in tokens:
            return key
    return None


@dataclass(frozen=True)
class Charge:
    """One occurrence of a series. The dates are the evidence behind every
    other field here — a claim about a rhythm should be inspectable."""

    date: date
    amount: Decimal


@dataclass(frozen=True)
class RecurringGroup:
    """One detected series. `label` is display text (the latest description,
    so aliases show); `key` is the internal grouping identity."""

    key: str
    label: str
    occurrences: int
    frequency: str  # weekly | biweekly | monthly | bimonthly | semiannual | yearly
    typical_amount: Decimal
    #: What this series costs per 30 days, for ranking and for the total load.
    monthly_equivalent: Decimal
    #: Whether the amount barely moves charge to charge. A subscription is
    #: stable; an electricity bill recurs but varies — both belong here,
    #: labelled differently.
    amount_stable: bool
    last_date: date
    next_expected: date
    #: The series' dominant category, for coloring. None if uncategorized.
    category_id: UUID | None
    #: Every charge in the series, oldest first. The rhythm this service
    #: asserts is only trustworthy if the user can look at the days it was
    #: inferred from.
    charges: tuple[Charge, ...] = ()


#: A hand-typed name must be shared by at least this many charges before it
#: outranks the raw-text key. One rename must not pull a row out of an
#: otherwise intact series (see ``test_alias_changes_the_label_but_never_splits``).
_NAMED_GROUP_MIN = 2


class RecurrenceService:
    def __init__(self, min_occurrences: int = 3) -> None:
        self._min_occurrences = min_occurrences

    def detect(
        self,
        transactions: list[Transaction],
        aliases: list[tuple[str, str]] = [],
    ) -> list[RecurringGroup]:
        """`aliases` are the user's taught (label, alias) pairs. A taught
        label outranks the text heuristic as identity: naming a charge and
        grouping its series are the same act, so "PAYPAL *CABLEYCOMUN OPM"
        and "CABLEYCOMUN SA CV" merge the moment both match the user's
        «cableycomun».

        A display name the user typed on several rows is the same claim,
        even when the bank text never contained those words (a SPEI to
        the school that changes only the month).
        """
        aliaser = AliasService(aliases)

        named_counts: dict[str, int] = {}
        for tx in transactions:
            if tx.tx_type != TxType.EXPENSE or tx.excluded_from_stats:
                continue
            raw = tx.raw_description or ""
            desc = (tx.description or "").strip()
            if desc and desc != raw:
                named = normalize(desc)
                if named:
                    named_counts[named] = named_counts.get(named, 0) + 1

        groups: dict[str, list[Transaction]] = {}
        display: dict[str, str] = {}
        for tx in transactions:
            if tx.tx_type != TxType.EXPENSE or tx.excluded_from_stats:
                continue
            # Identity comes from the RAW text: the bank's wording is stable,
            # while `description` moves under aliases and hand edits — a
            # half-renamed series must not split in two.
            raw = tx.raw_description or tx.description or ""
            desc = (tx.description or "").strip()
            named = normalize(desc) if desc and desc != raw else ""
            utility = known_utility_key(raw)
            # A name the user typed on several rows wins over a taught alias.
            # Alias matching is a substring of the bank text; a short taught
            # label like "pago" would otherwise swallow every SPEI and hide
            # «Colegiatura Demian».
            # Known utilities win over that name: «Pago Luz» on two CFE
            # CONTIGO rows must not split them from unlabeled CFE SUM SERV.
            if utility:
                key = f"util:{utility}"
                if named:
                    display[key] = desc
            elif named and named_counts.get(named, 0) >= _NAMED_GROUP_MIN:
                key = f"named:{named}"
                display[key] = desc
            else:
                matched = aliaser.match(raw)
                if matched is not None:
                    label, alias = matched
                    key = f"alias:{label}"
                    display[key] = alias
                else:
                    key = series_key(raw)
            if not key:
                continue
            groups.setdefault(key, []).append(tx)

        results: list[RecurringGroup] = []
        for key, txs in groups.items():
            group = self._qualify(key, txs, display.get(key))
            if group is not None:
                results.append(group)

        results.sort(key=lambda g: g.monthly_equivalent, reverse=True)
        return results

    def _qualify(
        self, key: str, txs: list[Transaction], display: str | None = None
    ) -> RecurringGroup | None:
        if len(txs) < self._min_occurrences:
            return None

        txs.sort(key=lambda t: t.tx_date)
        # Two posts on the same day are a double capture (Mercado Pago
        # authorization + settlement), not two memberships. A 0-day gap
        # would fail the regularity check and hide a real monthly gym.
        txs = _one_per_day(txs)
        if len(txs) < self._min_occurrences:
            return None
        amounts = [abs(float(t.amount)) for t in txs]
        median_amount = statistics.median(amounts)
        if median_amount > 0 and len(txs) > self._min_occurrences:
            floor = _MICRO_CHARGE_FRACTION * median_amount
            bills = [t for t in txs if abs(float(t.amount)) >= floor]
            if len(bills) >= self._min_occurrences:
                txs = bills
        intervals = [
            (txs[i].tx_date - txs[i - 1].tx_date).days for i in range(1, len(txs))
        ]
        median_interval = statistics.median(intervals)
        if median_interval <= 0:
            # Same-day duplicates dominate; that is a burst, not a rhythm.
            return None

        frequency = next(
            (name for name, lo, hi in _FREQUENCY_WINDOWS if lo <= median_interval <= hi),
            None,
        )
        if frequency is None:
            return None

        # Regularity: most gaps must sit near the median. ±4 days absorbs
        # weekends and bank processing; the fraction absorbs one skipped month.
        tolerance = max(4.0, 0.25 * median_interval)
        near = sum(1 for d in intervals if abs(d - median_interval) <= tolerance)
        if near / len(intervals) < 0.6:
            return None

        amounts = [abs(float(t.amount)) for t in txs]
        typical = statistics.median(amounts)
        if typical <= 0:
            return None
        # Stability: median absolute deviation within 20% of the typical charge.
        mad = statistics.median(abs(a - typical) for a in amounts)
        amount_stable = mad <= 0.2 * typical

        typical_amount = Decimal(str(typical)).quantize(Decimal("0.01"))
        monthly_equivalent = Decimal(str(typical * 30 / median_interval)).quantize(
            Decimal("0.01")
        )

        # Dominant category: the mode over the series' rows.
        cat_counts: dict[UUID | None, int] = {}
        for t in txs:
            cat_counts[t.category_id] = cat_counts.get(t.category_id, 0) + 1
        category_id = max(cat_counts, key=lambda c: cat_counts[c])

        return RecurringGroup(
            key=key,
            # Alias-keyed groups show the alias; heuristic groups show the
            # latest description (alias-aware, freshest wording).
            label=display or txs[-1].description or txs[-1].raw_description,
            occurrences=len(txs),
            frequency=frequency,
            typical_amount=typical_amount,
            monthly_equivalent=monthly_equivalent,
            amount_stable=amount_stable,
            last_date=txs[-1].tx_date,
            next_expected=txs[-1].tx_date + timedelta(days=round(median_interval)),
            category_id=category_id,
            # `txs` is already sorted oldest-first by the cadence check above.
            charges=tuple(
                Charge(date=t.tx_date, amount=abs(t.amount)) for t in txs
            ),
        )
