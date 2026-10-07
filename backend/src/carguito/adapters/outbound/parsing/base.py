from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Matches a leading date like: 05/01/2024, 5-1-24, 05-ENE-24, 05 ENE 2024
_DATE_RE = re.compile(
    r"^\s*(?P<d>\d{1,2})[\s/\-.](?P<m>\d{1,2}|[A-Za-zÁÉÍÓÚáéíóú]{3,})"
    r"(?:[\s/\-.](?P<y>\d{2,4}))?"
)

# Matches money amounts: 1,234.56 / -45.50 / +45.50 / (99.00) / $12.00
_AMOUNT_RE = re.compile(r"[-+(]?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?")

_INCOME_HINTS = ("abono", "deposito", "depósito", "spei recibido", "nomina", "nómina")
_EXPENSE_HINTS = ("cargo", "compra", "retiro", "pago", "comision", "comisión")

#: ``sign_hint`` vocabulary. Statements disagree about how they mark direction,
#: so "the token carried no sign" has to be distinguishable from "the token was
#: explicitly positive" -- otherwise an unsigned line looks like income.
SIGN_NEGATIVE = -1
SIGN_NONE = 0
SIGN_POSITIVE = 1


def parse_amount(token: str) -> tuple[Decimal, int] | None:
    """Split a money token into ``(magnitude, sign_hint)``.

    Returns the **unsigned** magnitude plus what the token said about
    direction, rather than a signed Decimal. Callers must not reconstruct a
    signed amount from this: direction is `tx_type`'s job, and the hint is one
    input to deciding it (see :func:`infer_tx_type`).

    ``-45.50`` and ``(99.00)`` both yield ``SIGN_NEGATIVE``; ``+45.50`` yields
    ``SIGN_POSITIVE``; a bare ``45.50`` yields ``SIGN_NONE``.
    """
    raw = token.strip()
    if raw.startswith(("-", "(")):
        sign_hint = SIGN_NEGATIVE
    elif raw.startswith("+"):
        sign_hint = SIGN_POSITIVE
    else:
        sign_hint = SIGN_NONE

    cleaned = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    cleaned = cleaned.replace(" ", "").lstrip("-+")
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    # A token like "-45.50" is a magnitude of 45.50 pointing outwards, never
    # a negative magnitude.
    return abs(value), sign_hint


def parse_date(day: str, month: str, year: str | None, default_year: int) -> date | None:
    try:
        d = int(day)
    except ValueError:
        return None

    month = month.strip().lower()
    if month.isdigit():
        m = int(month)
    else:
        m = SPANISH_MONTHS.get(month[:3])
    if not m or not (1 <= m <= 12):
        return None

    if year:
        y = int(year)
        if y < 100:
            y += 2000
    else:
        y = default_year

    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_leading_date(line: str, default_year: int) -> tuple[date, str] | None:
    """Return (date, remainder-of-line) if the line begins with a date."""
    match = _DATE_RE.match(line)
    if not match:
        return None
    parsed = parse_date(match.group("d"), match.group("m"), match.group("y"), default_year)
    if parsed is None:
        return None
    return parsed, line[match.end():].strip()


def find_amounts(text: str) -> list[tuple[Decimal, int]]:
    """Every money token in ``text`` as ``(magnitude, sign_hint)`` pairs."""
    amounts = []
    for token in _AMOUNT_RE.findall(text):
        parsed = parse_amount(token)
        if parsed is not None:
            amounts.append(parsed)
    return amounts


def infer_tx_type(description: str, sign_hint: int = SIGN_NONE) -> str:
    """Classify a statement line as ``"income"`` or ``"expense"``.

    Precedence, highest first:

    1. **Sign hint.** If the statement bothered to mark the token's direction,
       that is a fact about this line and beats a guess from wording. A
       description containing "PAGO" on a ``+1,200.00`` credit is a refund.
    2. **Keyword.** Spanish income wording ("abono", "spei recibido",
       "nómina", ...).
    3. **Default expense.** Most line items on a statement are charges.

    The old implementation took the *signed amount* and then ignored it
    entirely, which is what let sign and type disagree.
    """
    if sign_hint == SIGN_NEGATIVE:
        return "expense"
    if sign_hint == SIGN_POSITIVE:
        return "income"

    lowered = description.lower()
    if any(h in lowered for h in _INCOME_HINTS):
        return "income"
    return "expense"
