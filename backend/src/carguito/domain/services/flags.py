"""Derived flags read off a bank description (docs/redesign-plan.md §2, §3).

Two facts about a movement that no statement states outright and that both
change headline numbers:

**Is it a transfer between the user's own accounts?** A "PAGO TC" on the debit
statement is the same money as the card's own charges, so counting both doubles
it. `is_transfer` is excluded by default from every spend measure.

**Is it cash coming out of an ATM?** Metric 4. The plan is explicit that this
must be a *flag*, not a category keyword: a withdrawal's category is unknown --
the money was spent on something the statement cannot see.

Both are **conservative on purpose**, and in opposite ways.

*Transfers* match only explicit card-payment / traspaso wording. A plain
"TRANSFERENCIA" or "SPEI" to a third party is rent, or a friend, or a
contractor -- real money leaving. Treating those as transfers would silently
delete a large share of someone's spending, which is a worse failure than
leaving a card payment double-counted, because it is invisible.

*Withdrawals* exclude fees. "COMISION RETIRO" is what the bank charged you for
the withdrawal; it is not cash in your pocket, and metric 4 claims to say how
much cash you took out (§3: "Split out `comision retiro` — the fee isn't
withdrawn cash").

Pure domain: a string in, two booleans out. No repository, no I/O -- same shape
as ``categorization.py``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")

#: Explicit "I paid my own card" / "I moved money between my own accounts"
#: wording. Nothing else — a bare "transferencia"/"spei" to a third party is
#: rent, or a friend: real money leaving. `pago tarjeta` also covers "pago
#: tarjeta de credito".
#:
#: - "su abono" is the card statement acknowledging the payment YOU made into
#:   it ("SU ABONO...GRACIAS") — the incoming half of a self-transfer. Salary
#:   lines say "abono nomina", never "su abono", so the pronoun is the anchor.
#: - "cajita" is Nu's own savings pocket: money moving to or from it never
#:   left the user.
#: - "pago de servicio NNNNNN a tb" is how a Banamex debit account records a
#:   payment to a Banamex card ("TB": Tarjeta Banamex) -- the outgoing half of
#:   paying your own card. The reference number between the words is what the
#:   plain "pago tarjeta" pattern could not see past.
_TRANSFER = re.compile(
    r"\b(?:"
    r"pago\s+(?:de\s+)?(?:tc|tdc|tarjeta)"
    r"|pago\s+de\s+servicio\s+\d+\s+a\s+tb"
    r"|traspaso"
    r"|su\s+abono"
    r"|cajita"
    r")\b"
)

#: ATM wording. `\b` on `atm` matters -- an unanchored substring would fire on
#: any description that happens to contain those three letters.
_WITHDRAWAL = re.compile(
    r"\b(?:"
    r"retiro|retiros"
    r"|cajero|cajeros"
    r"|atm"
    r"|disp(?:osicion)?\s+(?:de\s+)?efectivo"
    r")\b"
)

#: A fee *about* a withdrawal is not a withdrawal. This wins over
#: :data:`_WITHDRAWAL` rather than merely competing with it.
_FEE = re.compile(r"\b(?:comision|comisiones|cargo\s+por\s+servicio)\b")


@dataclass(frozen=True)
class TransactionFlags:
    """Independent, not exclusive: nothing says a row cannot be neither."""

    is_transfer: bool = False
    is_cash_withdrawal: bool = False


def normalize_description(description: str | None) -> str:
    """Fold accents and case so "COMISIÓN" and "comision" are one thing."""
    if not description:
        return ""
    folded = unicodedata.normalize("NFKD", description).encode("ascii", "ignore").decode()
    return _WHITESPACE.sub(" ", folded.lower()).strip()


def is_transfer(description: str | None) -> bool:
    return bool(_TRANSFER.search(normalize_description(description)))


def is_cash_withdrawal(description: str | None) -> bool:
    text = normalize_description(description)
    if _FEE.search(text):
        # "COMISION RETIRO CAJERO" is the bank's charge, not the cash.
        return False
    if _TRANSFER.search(text):
        # "Retiro de Cajita" moves money between the user's own pockets —
        # no bill left an ATM. A transfer is never a cash withdrawal.
        return False
    return bool(_WITHDRAWAL.search(text))


def detect_flags(description: str | None) -> TransactionFlags:
    """Both flags for one description. The single entry point ingest uses."""
    return TransactionFlags(
        is_transfer=is_transfer(description),
        is_cash_withdrawal=is_cash_withdrawal(description),
    )
