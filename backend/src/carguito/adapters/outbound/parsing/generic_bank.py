from __future__ import annotations

import re
from datetime import date

from ....application.dtos.extraction import ExtractedDocument, ParsedStatement, ParsedTransaction
from ....domain.value_objects.enums import SourceType, TxType
from .base import find_amounts, find_leading_date, infer_tx_type

_YEAR_RE = re.compile(r"\b(20\d{2})\b")


class TextStatementParser:
    """Line-oriented parser for text-extracted bank statements.

    Each transaction line is expected to begin with a date and contain at
    least one monetary amount. Subclasses tune ``template_key`` / ``bank``.
    """

    template_key = "generic_bank"
    bank: str | None = None

    def parse(self, doc: ExtractedDocument) -> ParsedStatement:
        default_year = self._detect_year(doc.text)
        txs: list[ParsedTransaction] = []
        dates: list[date] = []

        for line in doc.lines or doc.text.splitlines():
            found = find_leading_date(line, default_year)
            if not found:
                continue
            tx_date, remainder = found
            amounts = find_amounts(remainder)
            if not amounts:
                continue

            amount, sign_hint = amounts[0]
            # Strip the amount tokens from the description text.
            description = self._clean_description(remainder)
            if not description:
                continue

            # `amount` is already an unsigned magnitude out of parse_amount;
            # the sign it carried is the strongest signal for direction.
            tx_type = infer_tx_type(description, sign_hint)
            txs.append(
                ParsedTransaction(
                    tx_date=tx_date,
                    amount=amount,
                    raw_description=description,
                    tx_type=TxType(tx_type),
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
    def _detect_year(text: str) -> int:
        match = _YEAR_RE.search(text or "")
        return int(match.group(1)) if match else date.today().year

    @staticmethod
    def _clean_description(remainder: str) -> str:
        from .base import _AMOUNT_RE  # local import to reuse the compiled regex

        without_amounts = _AMOUNT_RE.sub(" ", remainder)
        return " ".join(without_amounts.split()).strip()


class GenericBankParser(TextStatementParser):
    template_key = "generic_bank"
    bank = None
