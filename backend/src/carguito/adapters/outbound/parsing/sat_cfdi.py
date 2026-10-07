from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar
from xml.etree import ElementTree as ET

from ....application.dtos.extraction import ExtractedDocument, ParsedStatement, ParsedTransaction
from ....domain.value_objects.enums import SourceType, TxType


class SatCfdiParser:
    """Parses SAT CFDI XML (Mexican digital tax invoices).

    A single upload may contain one CFDI. Because attributes in CFDI are not
    namespaced (only element tags are), we match tags by local name to be
    resilient across CFDI 3.3 / 4.0.
    """

    template_key = "sat_cfdi"

    #: ``TipoDeComprobante`` -> direction, from the *receiver's* perspective.
    #:
    #: ``I`` (ingreso)  the issuer's income, so the user's money going out.
    #: ``E`` (egreso)   a credit note / refund, so money coming back.
    #: ``N`` (nómina)   a payroll receipt: the user is being paid. INCOME.
    #:                  This used to fall through to the else branch and be
    #:                  booked as an expense, i.e. a salary that *reduced* net
    #:                  worth.
    _TYPE_TO_TX_TYPE: ClassVar[dict[str, TxType]] = {
        "I": TxType.EXPENSE,
        "E": TxType.INCOME,
        "N": TxType.INCOME,
    }

    #: Types that move no money and must produce **no transaction**.
    #:
    #: ``P`` (pago)      a payment-complement, which settles a previously
    #:                   issued ``I``. Booking it double-counts that invoice.
    #: ``T`` (traslado)  a goods-in-transit receipt. No payment at all.
    #:
    #: The document is still parsed and the statement still recorded, so the
    #: upload is not silently lost -- it just contributes zero transactions.
    _NON_MONETARY_TYPES = frozenset({"P", "T"})

    def parse(self, doc: ExtractedDocument) -> ParsedStatement:
        if not doc.xml:
            return ParsedStatement(source_type=SourceType.SAT_XML, transactions=[])

        root = ET.fromstring(doc.xml)
        comprobante = self._find_local(root, "Comprobante")
        if comprobante is None:
            comprobante = root

        total = self._decimal(comprobante.get("Total"))
        fecha = self._date(comprobante.get("Fecha"))
        tipo = (comprobante.get("TipoDeComprobante") or "I").upper()

        emisor = self._find_local(root, "Emisor")
        description = (
            (emisor.get("Nombre") if emisor is not None else None)
            or (emisor.get("Rfc") if emisor is not None else None)
            or "CFDI"
        )

        transactions: list[ParsedTransaction] = []
        if tipo not in self._NON_MONETARY_TYPES and total is not None and fecha is not None:
            transactions.append(
                ParsedTransaction(
                    tx_date=fecha,
                    # Magnitude only: direction lives in tx_type. A CFDI Total
                    # is already unsigned, but abs() makes the contract local
                    # instead of an assumption about the SAT's formatting.
                    amount=abs(total),
                    raw_description=description,
                    tx_type=self._TYPE_TO_TX_TYPE.get(tipo, TxType.EXPENSE),
                )
            )

        return ParsedStatement(
            source_type=SourceType.SAT_XML,
            bank="SAT",
            transactions=transactions,
            period_start=fecha,
            period_end=fecha,
        )

    @staticmethod
    def _find_local(root: ET.Element, local_name: str) -> ET.Element | None:
        if root.tag.rsplit("}", 1)[-1] == local_name:
            return root
        for el in root.iter():
            if el.tag.rsplit("}", 1)[-1] == local_name:
                return el
        return None

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
