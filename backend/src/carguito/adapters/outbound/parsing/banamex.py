from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ....application.dtos.extraction import ExtractedDocument, ParsedStatement, ParsedTransaction
from ....domain.value_objects.enums import SourceType, TxType
from .generic_bank import TextStatementParser

_MONTHS = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}
_MONEY = r"\d{1,3}(?:,\d{3})*\.\d{2}"

#: A movement starts with "DD MON " and the first words of its concept.
_START = re.compile(r"^(\d{2}) (ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC) (.+)$")
#: ...and ends on the line that carries its amount and the running balance.
_CLOSE = re.compile(rf"^(?P<text>.*?)\s*(?P<amount>{_MONEY})\s+(?P<balance>{_MONEY})$")
#: A line with only a balance: the opening balance, or a zero-amount notice
#: ("EXENCION COBRO COMISION", "DISPOSICIONES EN CAJERO EXENTAS").
_BALANCE_ONLY = re.compile(rf"^(?P<text>.*?)\s*(?P<balance>{_MONEY})$")

_DETAIL_HEADER = "DETALLE DE OPERACIONES"
_COLUMNS = "FECHA CONCEPTO RETIROS DEPOSITOS SALDO"
_PERIOD = re.compile(r"RESUMEN DEL (\d{2})/([A-Z]{3})/(\d{4}) AL (\d{2})/([A-Z]{3})/(\d{4})")
#: The section that follows the detail. Reaching it closes the last block.
_END_OF_DETAIL = re.compile(r"^(GRAFICO TRANSACCIONAL|RESUMEN DE COMISIONES|COMISIONES COBRADAS)")

#: The bank's disclaimer on every outgoing SPEI. Legal boilerplate, and a
#: trap for short category labels matched by substring ("ado" sits inside
#: "verificado"): it is not part of what the movement says.
_DISCLAIMER = re.compile(r"\(DATO\s+NO\s+VERIFICADO\s+POR\s+ESTA\s+INSTITUCION\)")

#: Every sheet opens with "ESTADO DE CUENTA AL ..." and, on detail pages,
#: reaches "DETALLE DE OPERACIONES" a few lines later. Everything between the
#: two is page furniture -- client number, page count, the customer's name, the
#: call-centre lines -- and is skipped as a *zone* rather than matched line by
#: line, so no personal detail has to be spelled out here to be ignored.
_PAGE_START = "ESTADO DE CUENTA AL"
#: The footer code and the column header, which sit outside that zone.
_PAGE_NOISE = re.compile(r"^(FECHA CONCEPTO|\d{6}\.B\d{2}[A-Z0-9.]+)")
#: Inside a movement, the lines that are plumbing rather than meaning: branch,
#: teller, authorisation, time, tracking keys, bare account numbers.
_DETAIL_NOISE = re.compile(
    r"^(SUC \d|CAJA \d|HORA \d|RASTREO|REF\.\s?\d|CTA\.(ORDENANTE|BENEFICIARIO)$"
    r"|[A-Z0-9]{18,}$|\d{6,}$|\d{6,}\s+REF\.\d+$|SUC \d+ CAJA)"
)


class BanamexParser(TextStatementParser):
    """Citibanamex statements.

    Two layouts arrive under this bank. The card statements are date-prefixed
    one-line items that the shared :class:`TextStatementParser` reads. The
    **debit** statement ("MiCuenta") is a different animal: one movement is a
    *block* of two to twenty lines, its amount sits on the block's last line
    next to the running balance, and the RETIROS / DEPOSITOS columns collapse
    into one number when the PDF is read as text. Direction is recovered from
    the balance -- it went up by the amount or down by it -- which is also what
    makes the parse self-checking against the statement's own totals.
    """

    template_key = "banamex"
    bank = "Banamex"

    def parse(self, doc: ExtractedDocument) -> ParsedStatement:
        text = doc.text or ""
        if _DETAIL_HEADER in text and _COLUMNS in text:
            return self._parse_debit(doc)
        return super().parse(doc)

    # --- the debit layout ----------------------------------------------------
    def _parse_debit(self, doc: ExtractedDocument) -> ParsedStatement:
        text = doc.text or ""
        lines = [line.strip() for line in (doc.lines or text.splitlines())]
        period_start, period_end = _period(text)
        # Movements print "DD MON" with no year; the period's end year is the
        # year, except for months that fall after it (a December inside a
        # statement cut in January).
        end_year = period_end.year if period_end else date.today().year
        end_month = period_end.month if period_end else 12

        txs: list[ParsedTransaction] = []
        balance: Decimal | None = None
        block: list[str] | None = None
        block_date: date | None = None
        in_detail = False

        def close() -> None:
            """Settle the open block on its last money-bearing line.

            Not on its last line: a block that runs past a page break has the
            next page's furniture after its amount, and a zero-amount notice
            has only a balance. Anything after the money is not the movement.
            """
            nonlocal balance, block, block_date
            if block is None:
                return
            idx = next(
                (i for i in range(len(block) - 1, -1, -1)
                 if _CLOSE.match(block[i]) or _BALANCE_ONLY.match(block[i])),
                None,
            )
            if idx is None:
                block, block_date = None, None
                return
            last = block[idx]
            body = block[:idx]
            m2 = _CLOSE.match(last)
            if m2:
                amount, new_balance = _money(m2.group("amount")), _money(m2.group("balance"))
                body = body + [m2.group("text")]
            else:
                m1 = _BALANCE_ONLY.match(last)
                amount, new_balance = Decimal(0), _money(m1.group("balance"))
                body = body + [m1.group("text")]
            if amount > 0 and block_date is not None and not body[0].startswith("SALDO ANTERIOR"):
                # The two columns collapsed into one number; the balance says
                # which it was. A delta that matches neither is kept as an
                # expense but flagged nowhere else -- see the totals check in
                # the tests, which is the honest place to catch it.
                if balance is not None and new_balance == balance + amount:
                    kind = TxType.INCOME
                elif balance is not None and new_balance == balance - amount:
                    kind = TxType.EXPENSE
                else:
                    kind = TxType.EXPENSE
                txs.append(
                    ParsedTransaction(
                        tx_date=block_date,
                        amount=amount,
                        raw_description=_describe(body),
                        tx_type=kind,
                    )
                )
            balance = new_balance
            block, block_date = None, None

        in_header = False
        for line in lines:
            if not line:
                continue
            if line.startswith(_PAGE_START):
                in_header = True
                continue
            if _DETAIL_HEADER in line:
                in_header, in_detail = False, True
                continue
            if in_header or not in_detail or _PAGE_NOISE.match(line):
                continue
            if _END_OF_DETAIL.match(line):
                close()
                in_detail = False
                continue

            start = _START.match(line)
            if start:
                # A new movement while one is still open: the open one carried
                # no amount line, so it was a zero-amount notice. Its trailing
                # balance still counts.
                close()
                day, mon = int(start.group(1)), _MONTHS[start.group(2)]
                year = end_year if mon <= end_month else end_year - 1
                try:
                    block_date = date(year, mon, day)
                except ValueError:
                    block_date = None
                block = [start.group(3)]
                line = start.group(3)
            elif block is None:
                continue
            else:
                block.append(line)

            if _CLOSE.match(line):
                close()
        close()

        return ParsedStatement(
            source_type=SourceType.BANK_PDF,
            bank=self.bank,
            transactions=txs,
            period_start=period_start or (min(t.tx_date for t in txs) if txs else None),
            period_end=period_end or (max(t.tx_date for t in txs) if txs else None),
        )


def _period(text: str) -> tuple[date | None, date | None]:
    m = _PERIOD.search(text)
    if not m:
        return None, None
    try:
        start = date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
        end = date(int(m.group(6)), _MONTHS[m.group(5)], int(m.group(4)))
    except (KeyError, ValueError):
        return None, None
    return start, end


def _money(token: str) -> Decimal:
    return Decimal(token.replace(",", ""))


def _describe(body: list[str]) -> str:
    """The movement's own words, without the plumbing.

    Kept raw and long enough to carry the counterparty and the concept ("PAGO
    RECIBIDO DE NU MEXICO POR ORDEN DE ... Transferencia"): aliasing and
    categorisation work on this text downstream, and a description trimmed to
    the first line would lose exactly the part that names who paid.
    """
    # The bank's disclaimer on every outgoing SPEI. Legal boilerplate, and a
    # trap for short category labels matched by substring ("ado" is inside
    # "verificado"): it is not part of what the movement says.
    kept = []
    for line in body:
        line = line.strip()
        if not line or _DETAIL_NOISE.match(line):
            continue
        # "Nomina 2Q Noviembre RASTREO:" -- the concept, with the label of the
        # tracking key that follows it on the next line.
        line = re.sub(r"\s*RASTREO:?\s*$", "", line)
        if line:
            kept.append(line)
    joined = " ".join(" ".join(kept).split())
    joined = _DISCLAIMER.sub(" ", joined)
    return " ".join(joined.split())[:160]
