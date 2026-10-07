"""What a credit-card statement asks to be paid, and by when.

A card statement carries three figures the movement list never will: the
payment that avoids interest, the minimum payment, and the day both are due.
For someone reading their own statement for the first time, the due date is
the single most consequential number on the page -- and the one Tomin could
not show, because the parsers read movements and nothing else.

This reads those figures off the text of *any* statement, bank-agnostic, by
the Spanish labels the issuers print ("Pago para no generar intereses", "Pago
mínimo", "Fecha límite de pago"). A debit statement has none of them and
yields ``None``. Nothing here decides whether the account *is* a card -- that
stays the user's declaration -- it only reports what the paper says.

Conservative on purpose: a label without a readable figure next to it is
reported as absent, never guessed. An absent figure renders as "pendiente de
leer" downstream; a wrong one would render as a bill.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Amount: "$1,234.56", "1,234.56", "$ 1234.56". Two decimals required, so a
# folio or a date fragment next to the label cannot pass for money.
_AMOUNT = r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+\.[0-9]{2})"

# Date: "12/SEP/2026", "12-sep-26", "12 de septiembre de 2026", "12/09/2026".
_DATE = (
    r"([0-3]?[0-9])\s*(?:de\s+)?[/\-\s]?\s*([a-z]{3,10}|[01]?[0-9])\s*(?:de\s+)?[/\-\s]?\s*"
    r"((?:19|20)[0-9]{2}|[0-9]{2})\b"
)

_NO_INTEREST = re.compile(
    r"pago\s+para\s+no\s+generar\s+intereses\W{0,20}?" + _AMOUNT, re.IGNORECASE
)
_MINIMUM = re.compile(r"pago\s+minimo\W{0,20}?" + _AMOUNT, re.IGNORECASE)
_DUE = re.compile(r"fecha\s+limite\s+de\s+pago\W{0,20}?" + _DATE, re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CreditSummary:
    no_interest_payment: Decimal | None
    minimum_payment: Decimal | None
    due_date: date | None

    @property
    def empty(self) -> bool:
        return (
            self.no_interest_payment is None
            and self.minimum_payment is None
            and self.due_date is None
        )


def read_credit_summary(text: str) -> CreditSummary | None:
    """The card figures printed in ``text``, or ``None`` when there are none."""
    if not text:
        return None
    flat = _fold(text)
    summary = CreditSummary(
        no_interest_payment=_amount(_NO_INTEREST, flat),
        minimum_payment=_amount(_MINIMUM, flat),
        due_date=_due_date(flat),
    )
    return None if summary.empty else summary


def _fold(text: str) -> str:
    """Lowercase, accents stripped, whitespace collapsed: the labels are
    matched by their letters, not by how the PDF happened to space them."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", stripped.lower())


def _amount(pattern: re.Pattern[str], flat: str) -> Decimal | None:
    m = pattern.search(flat)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _due_date(flat: str) -> date | None:
    m = _DUE.search(flat)
    if not m:
        return None
    day_s, month_s, year_s = m.group(1), m.group(2), m.group(3)
    month = _MONTHS.get(month_s[:3]) if month_s.isalpha() else _int(month_s)
    day, year = _int(day_s), _int(year_s)
    if month is None or day is None or year is None:
        return None
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _int(s: str) -> int | None:
    try:
        return int(s)
    except ValueError:
        return None
