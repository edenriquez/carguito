from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from ....application.dtos.extraction import ExtractedDocument, ParsedStatement, ParsedTransaction
from ....domain.value_objects.enums import SourceType, TxType

#: A movement's date and concept: "13/02/2026 TRANSFERENCIA SPEI A SU FAVOR".
_DATE_LINE = re.compile(r"^\s*(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{4})\s*(?P<concept>.*)$")

#: The amount, with the direction spelled out: "(+) $5,500.00 SPEI". The channel
#: that trails it ("SPEI", "BANCO AZTECA", "COMPRA CON") is the statement's
#: "Lugar o Canal de Operación" column, not part of the concept.
_AMOUNT = re.compile(r"\((?P<sign>[+-])\)\s*\$(?P<amount>[\d,]+\.\d{2})\s*(?P<channel>.*?)\s*$")

#: Same amount, anywhere in a line rather than filling it.
_AMOUNT_INLINE = re.compile(r"\((?P<sign>[+-])\)\s*\$(?P<amount>[\d,]+\.\d{2})")


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


class BancoAztecaParser:
    """Parser for Banco Azteca statements, which are laid out in blocks.

    Azteca prints one movement as a *group* of lines rather than one row:

        (+) $5,500.00 SPEI
        11/02/2026 TRANSFERENCIA SPEI A SU FAVOR
        EMISOR: BANAMEX
        CUENTA: 002180903198971422
        ...

    The date/concept and the amount land on separate lines, and which comes
    first depends on the column geometry of that page — reading order puts the
    amount before the date about as often as after it. On a real 8-page
    statement the split was 18 amounts on the following line, 4 on the preceding
    one, and 7 that happened to merge into the date line.

    ``generic_bank`` requires the date and the amount on one line, so it found
    those 7 and silently dropped the other 22 — a statement that looked parsed
    but was missing three quarters of its movements. That is the failure this
    parser exists to prevent.

    The pairing is unambiguous: every date line owns exactly one amount, found
    inline, on the next line, or on the previous one, and each amount line is
    claimed once. Direction is read from the statement's own ``(+)``/``(-)``
    marker instead of being guessed from wording.
    """

    template_key = "banco_azteca"
    bank = "Banco Azteca"

    def parse(self, doc: ExtractedDocument) -> ParsedStatement:
        lines = list(doc.lines or (doc.text or "").splitlines())

        # Index the standalone amount lines first, so a date line can look
        # either way for its partner. `claimed` keeps two neighbouring dates
        # from both taking the same amount.
        standalone: dict[int, re.Match[str]] = {}
        for i, line in enumerate(lines):
            if _DATE_LINE.match(line):
                continue
            match = _AMOUNT.match(line.strip())
            if match:
                standalone[i] = match

        claimed: set[int] = set()
        txs: list[ParsedTransaction] = []
        dates: list[date] = []

        for i, line in enumerate(lines):
            date_match = _DATE_LINE.match(line)
            if not date_match:
                continue

            concept = date_match.group("concept").strip()

            # 1. Amount on the date line itself.
            amount_match: re.Match[str] | None = _AMOUNT_INLINE.search(concept)
            channel = ""
            if amount_match:
                channel = concept[amount_match.end() :].strip()
                concept = concept[: amount_match.start()].strip()
            else:
                # 2. Next line, then 3. previous line — the order the real
                # statement favours, so the common case never depends on the
                # fallback.
                for neighbour in (i + 1, i - 1):
                    if neighbour in standalone and neighbour not in claimed:
                        amount_match = standalone[neighbour]
                        channel = amount_match.group("channel").strip()
                        claimed.add(neighbour)
                        break

            if amount_match is None:
                # A date with no amount anywhere near it is a period or a
                # cut-off date, not a movement.
                continue

            amount = _to_decimal(amount_match.group("amount"))
            if amount is None:
                continue

            tx_date = self._to_date(date_match)
            if tx_date is None:
                continue

            description = concept or channel
            if not description:
                continue

            txs.append(
                ParsedTransaction(
                    tx_date=tx_date,
                    amount=amount,
                    raw_description=description,
                    tx_type=(
                        TxType.INCOME if amount_match.group("sign") == "+" else TxType.EXPENSE
                    ),
                )
            )
            dates.append(tx_date)

        return ParsedStatement(
            source_type=SourceType.BANK_PDF,
            bank=self.bank,
            transactions=txs,
            period_start=min(dates) if dates else None,
            period_end=max(dates) if dates else None,
        )

    @staticmethod
    def _to_date(match: re.Match[str]) -> date | None:
        try:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        except ValueError:
            return None
