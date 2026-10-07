"""Deciding which movement a photographed ticket belongs to.

The ticket says ``SORIANA · 22/08/2026 · $141.60``; the ledger says
``SORIANA HIPER MIXCOAC · 22 ago · $141.60``. Joining those two is the entire
value of the feature — a receipt that is not attached to a movement is a photo,
and a movement with its receipt attached is a grocery bill you can ask
questions about.

The rule is deliberately strict about money and lenient about everything else:

* **The total must match.** A receipt whose total is not on the statement is
  not that purchase, however close the date. Cards round nothing, and a tip or
  a cash-back would make it a different amount honestly.
* The date narrows, it does not decide: a card charge settles a day or two
  after the ticket prints, so a window is required, and inside that window the
  closest day wins.
* The store name only breaks ties. OCR mangles logos, and banks write
  ``SORIANA HIPER 4062 MEXICO`` — agreement is evidence, disagreement is not.

An ambiguous best guess is **not** applied. Two identical charges on the same
day are exactly the case where a wrong attachment would be invisible and
permanent, so the receipt stays unattached and the user is asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from ..entities.receipt import Receipt
from ..entities.transaction import Transaction
from ..value_objects.enums import TxType
from .categorization import normalize

#: How far a card charge may settle from the day the ticket printed.
WINDOW_DAYS = 4

#: How many centavos apart two "equal" totals may be. Not zero because OCR
#: reads a smudged ``0`` as an ``8`` often enough to matter, and not more than
#: a peso because beyond that it is a different purchase.
TOLERANCE = Decimal("1.00")

#: The gap the winner needs over the runner-up to be attached without asking.
DECISIVE_MARGIN = 10


@dataclass(frozen=True)
class MatchCandidate:
    transaction_id: UUID
    score: int
    #: Why this row scored what it did, in the user's language. Shown next to
    #: the choice when the user has to pick.
    reason: str


def match_receipt(
    receipt: Receipt, transactions: list[Transaction]
) -> tuple[UUID | None, list[MatchCandidate]]:
    """Return ``(auto-attach id or None, candidates worth showing)``.

    Both halves are useful: the id is what ingest applies, and the candidates
    are what the phone offers when there is no id to apply.
    """
    if receipt.total is None or receipt.purchased_at is None:
        # Without a total there is nothing to match on, and without a date the
        # window that keeps the match honest does not exist.
        return (None, [])

    candidates: list[MatchCandidate] = []
    for transaction in transactions:
        if transaction.tx_type is not TxType.EXPENSE:
            continue
        if transaction.is_transfer or transaction.excluded_from_stats:
            continue
        days = abs((transaction.tx_date - receipt.purchased_at).days)
        if days > WINDOW_DAYS:
            continue
        gap = abs(transaction.amount - receipt.total)
        if gap > TOLERANCE:
            continue

        score = 60 if gap == 0 else 45
        score += max(0, 20 - days * 5)
        reasons = ["mismo monto" if gap == 0 else f"monto a ${gap} de diferencia"]
        reasons.append("mismo día" if days == 0 else f"{days} día{'s' if days > 1 else ''} después")
        if _store_agrees(receipt.store, transaction):
            score += 15
            reasons.append("misma tienda")
        candidates.append(
            MatchCandidate(
                transaction_id=transaction.id,
                score=score,
                reason=", ".join(reasons),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    if not candidates:
        return (None, [])
    if len(candidates) == 1 or candidates[0].score - candidates[1].score >= DECISIVE_MARGIN:
        return (candidates[0].transaction_id, candidates)
    # A tie is a question, not a coin flip.
    return (None, candidates)


def _store_agrees(store: str | None, transaction: Transaction) -> bool:
    """True when a word of the store's name appears in the movement's text.

    Words of three letters or fewer are ignored: "la" in "LA COMER" matches
    half the ledger.
    """
    if not store:
        return False
    text = normalize(f"{transaction.description or ''} {transaction.raw_description}")
    return any(word in text for word in normalize(store).split() if len(word) > 3)
