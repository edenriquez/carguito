"""Charges worth a second look: the "mira aquí" behind the Movimientos chart.

Three rules, each explainable in one sentence, each carrying its own numbers,
because the chart draws a ring on a dot and the ring is a claim. Precision
over recall, like recurrence and the advisor: one false "cargo inusual" and
the user stops looking at the rings.

- **Monto inusual**: a charge at or above :data:`UNUSUAL_RATIO` times the
  median of the merchant's own earlier charges (at least
  :data:`UNUSUAL_MIN_PRIOR` of them). "3.2× lo que sueles gastar ahí" — the
  merchant's history is the baseline, never the whole ledger.
- **Posible duplicado**: same merchant, same amount, within
  :data:`DUPLICATE_GAP_DAYS`, unless the merchant is a weekly series (a
  Tuesday-and-Friday gym is not a double charge).
- **Comercio nuevo**: the merchant's first charge ever, large enough to
  matter — at or above the :data:`NEW_MERCHANT_PERCENTILE` of the user's
  recent expenses — and only once the ledger has enough history to make
  "first" meaningful.

Merchant identity is :func:`recurrence.series_key`, the same normalization
the recurrence detector and the rename suggestions use, so the three agree on
what "the same place" is.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from ..entities.transaction import Transaction
from ..value_objects.enums import TxType
from .recurrence import RecurrenceService, series_key

AttentionKind = Literal["unusual_amount", "possible_duplicate", "new_merchant"]

#: A charge this many times the merchant's median is unusual.
UNUSUAL_RATIO = Decimal("2.5")
#: Earlier charges needed before "what you usually spend there" means anything.
UNUSUAL_MIN_PRIOR = 3
#: Same merchant + same amount within this many days reads as a double charge.
DUPLICATE_GAP_DAYS = 3
#: A first-time merchant is only worth a ring above this share of recent spend.
NEW_MERCHANT_PERCENTILE = 0.9
#: ...and only once the ledger is at least this old — on day one everything is new.
NEW_MERCHANT_MIN_HISTORY_DAYS = 30
#: Recent-spend sample the percentile is taken over.
NEW_MERCHANT_LOOKBACK_DAYS = 90
NEW_MERCHANT_MIN_SAMPLE = 10


@dataclass(frozen=True)
class AttentionItem:
    transaction_id: UUID
    kind: AttentionKind
    #: One sentence in the user's language: the reason, with its numbers.
    reason: str
    #: unusual_amount: amount / merchant median. Others: None.
    ratio: Decimal | None
    #: The other leg(s) of a duplicate; empty otherwise.
    related_ids: tuple[UUID, ...]
    severity: Literal["warn", "info"]
    #: Ordering key: bigger money first within a severity.
    amount: Decimal


def _mxn(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${q:,.2f}"


def _eligible(t: Transaction) -> bool:
    return (
        t.tx_type is TxType.EXPENSE
        and not t.excluded_from_stats
        and not t.is_transfer
        and not t.is_cash_withdrawal
    )


def _key(t: Transaction) -> str:
    return series_key(t.raw_description or t.description or "")


def _percentile(values: list[Decimal], p: float) -> Decimal:
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return s[idx]


class AttentionService:
    def __init__(self, recurrence: RecurrenceService | None = None) -> None:
        self._recurrence = recurrence or RecurrenceService()

    def detect(
        self,
        history: list[Transaction],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[AttentionItem]:
        """Items for charges dated inside ``[start, end]``; baselines always
        come from the whole ``history``. One item per charge, the strongest
        rule wins (unusual > duplicate > new)."""
        rows = sorted((t for t in history if _eligible(t)), key=lambda t: (t.tx_date, str(t.id)))
        if not rows:
            return []

        def in_window(t: Transaction) -> bool:
            return (start is None or t.tx_date >= start) and (end is None or t.tx_date <= end)

        by_key: dict[str, list[Transaction]] = {}
        for t in rows:
            k = _key(t)
            if k:
                by_key.setdefault(k, []).append(t)

        weekly = {
            g.key
            for g in self._recurrence.detect(history)
            if g.frequency == "weekly"
        }

        found: dict[UUID, AttentionItem] = {}

        def keep(item: AttentionItem) -> None:
            # First rule to claim a charge keeps it; rules run in precedence order.
            found.setdefault(item.transaction_id, item)

        # --- Monto inusual -------------------------------------------------
        for group in by_key.values():
            for i, t in enumerate(group):
                prior = [x.amount for x in group[:i]]
                if len(prior) < UNUSUAL_MIN_PRIOR or not in_window(t):
                    continue
                med = Decimal(str(statistics.median(prior)))
                if med <= 0 or t.amount < med * UNUSUAL_RATIO:
                    continue
                ratio = (t.amount / med).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                keep(
                    AttentionItem(
                        transaction_id=t.id,
                        kind="unusual_amount",
                        reason=f"{ratio}× lo que sueles gastar ahí (tu cargo típico es {_mxn(med)})",
                        ratio=ratio,
                        related_ids=(),
                        severity="warn",
                        amount=t.amount,
                    )
                )

        # --- Posible duplicado ----------------------------------------------
        gap = timedelta(days=DUPLICATE_GAP_DAYS)
        for key, group in by_key.items():
            if key in weekly:
                continue
            for i, t in enumerate(group):
                if not in_window(t):
                    continue
                twins = [
                    x
                    for x in group[:i]
                    if x.amount == t.amount and t.tx_date - x.tx_date <= gap
                ]
                if not twins:
                    continue
                days = (t.tx_date - twins[-1].tx_date).days
                when = (
                    "el mismo día"
                    if days == 0
                    else "un día antes"
                    if days == 1
                    else f"{days} días antes"
                )
                keep(
                    AttentionItem(
                        transaction_id=t.id,
                        kind="possible_duplicate",
                        reason=f"Mismo monto que otro cargo ahí {when}",
                        ratio=None,
                        related_ids=tuple(x.id for x in twins),
                        severity="warn",
                        amount=t.amount,
                    )
                )

        # --- Comercio nuevo -------------------------------------------------
        first_day = rows[0].tx_date
        for group in by_key.values():
            t = group[0]
            if not in_window(t):
                continue
            if (t.tx_date - first_day).days < NEW_MERCHANT_MIN_HISTORY_DAYS:
                continue
            since = t.tx_date - timedelta(days=NEW_MERCHANT_LOOKBACK_DAYS)
            sample = [x.amount for x in rows if since <= x.tx_date < t.tx_date]
            if len(sample) < NEW_MERCHANT_MIN_SAMPLE:
                continue
            floor = _percentile(sample, NEW_MERCHANT_PERCENTILE)
            if t.amount < floor:
                continue
            keep(
                AttentionItem(
                    transaction_id=t.id,
                    kind="new_merchant",
                    reason=f"Primera vez ahí, y arriba de tu gasto típico ({_mxn(floor)})",
                    ratio=None,
                    related_ids=(),
                    severity="info",
                    amount=t.amount,
                )
            )

        order = {"warn": 0, "info": 1}
        return sorted(found.values(), key=lambda i: (order[i.severity], -i.amount))
