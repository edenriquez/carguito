"""Sizes as the outside world prints them, normalised to litres and kilos.

Shared by every reference source. A survey writes "BOTELLA 3 LT.", a store page
writes "7 L" or "500 g", and the one thing the two have in common is that a
shopper needs both as pesos per litre. Grams and millilitres are folded into
kilos and litres so a 500 g bag and a 1 kg bag land on the same axis.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

#: A size printed inside a product name. Case-insensitive; accepts "3 LT.",
#: "7L", "500 GR", "1.5 l", "750 ml".
SIZE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(KILOS?|KG|KGS|GRAMOS?|G|GR|GRS|LITROS?|L|LT|LTS|MILILITROS?|ML)\b", re.I
)

_TO_BASE = {
    "kg": ("kg", 1), "kgs": ("kg", 1), "kilo": ("kg", 1), "kilos": ("kg", 1),
    "g": ("kg", 1000), "gr": ("kg", 1000), "grs": ("kg", 1000), "gramo": ("kg", 1000), "gramos": ("kg", 1000),
    "l": ("l", 1), "lt": ("l", 1), "lts": ("l", 1), "litro": ("l", 1), "litros": ("l", 1),
    "ml": ("l", 1000), "mililitro": ("l", 1000), "mililitros": ("l", 1000),
}


def parse_size(text: str) -> tuple[Decimal, str] | None:
    """``("3", "l")`` out of "BOTELLA 3 LT. LÍQUIDO"; ``None`` when no size is printed."""
    match = SIZE.search(text or "")
    if not match:
        return None
    return to_base(match.group(1), match.group(2))


def to_base(amount: str | Decimal, unit: str) -> tuple[Decimal, str] | None:
    """A quantity in any printed unit as ``(size, "l" | "kg")``; ``None`` if unusable."""
    key = str(unit).strip().lower()
    if key not in _TO_BASE:
        return None
    base, factor = _TO_BASE[key]
    try:
        size = Decimal(str(amount).replace(",", ".")) / factor
    except (InvalidOperation, ValueError):
        return None
    if size <= 0:
        return None
    return size.normalize(), base


def money(value) -> Decimal | None:
    """A price as two-decimal pesos, or ``None`` for anything that is not one."""
    try:
        price = Decimal(str(value).replace("$", "").replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return price if price > 0 else None


def rank_per_unit(units, *, each: int = 4):
    """Cheapest first within each base, never across bases: pesos per litre and
    pesos per kilo are different numbers and sorting them together would put a
    500 g bag "below" a 7-litre jug for no reason a shopper could act on."""
    ranked = []
    for base in ("l", "kg", "pz"):
        same = sorted((u for u in units if u.unit == base), key=lambda u: u.per_unit)
        ranked.extend(same[:each])
    return tuple(ranked)
