"""Which movements of a re-uploaded period are actually new.

A bank lets you download the current month before it closes: on the 6th of
October the September PDF may be the final one, but the one uploaded on the
20th of September held only the first three weeks. Uploading the later file
must *complement* the ledger, not double it — the hash check cannot help,
since the two files differ byte for byte.

A movement counts as already present when the ledger holds one with the same
date, magnitude, direction, currency and description (whitespace and case
folded, since two downloads of the same bank can wrap a line differently).
The match is a **multiset**: two identical 45.50 coffees on the same day in
the new file against one in the ledger means one of them is new. Matching on
"exists at all" would silently drop the second coffee, which is the worse
failure — a missing peso is invisible, a duplicate one is at least visible.

Pure domain, same shape as ``flags.py``: values in, values out.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Protocol, TypeVar


class _Movement(Protocol):
    tx_date: date
    amount: Decimal
    raw_description: str
    currency: str

    @property
    def tx_type(self) -> object: ...


M = TypeVar("M", bound=_Movement)

MovementKey = tuple[date, Decimal, str, str, str]


def movement_key(m: _Movement) -> MovementKey:
    tx_type = getattr(m.tx_type, "value", m.tx_type)
    return (
        m.tx_date,
        # Decimal("45.5") and Decimal("45.50") hash alike, but normalize()
        # keeps the key printable and stable across parsers.
        Decimal(m.amount).normalize(),
        str(tx_type),
        (m.currency or "").upper(),
        " ".join(m.raw_description.split()).casefold(),
    )


def split_new(incoming: Iterable[M], existing: Iterable[_Movement]) -> tuple[list[M], int]:
    """``(new movements, how many were already in the ledger)``.

    ``incoming`` keeps its order; each ledger row can absorb at most one
    incoming movement.
    """
    stock = Counter(movement_key(e) for e in existing)
    fresh: list[M] = []
    skipped = 0
    for m in incoming:
        k = movement_key(m)
        if stock[k] > 0:
            stock[k] -= 1
            skipped += 1
        else:
            fresh.append(m)
    return fresh, skipped
