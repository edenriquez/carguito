from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ...domain.value_objects.enums import SourceType, TransactionStatus, TxType


@dataclass(frozen=True)
class ExtractedDocument:
    """Raw content extracted from an uploaded file, before template parsing.

    Produced by an :class:`Extractor` adapter. ``kind`` tells downstream
    components whether to expect free text (bank PDFs/OCR) or structured XML
    (SAT CFDI).
    """

    kind: str  # "text" | "xml"
    filename: str
    text: str = ""
    lines: list[str] = field(default_factory=list)
    xml: str | None = None
    mime: str | None = None


@dataclass
class ParsedTransaction:
    tx_date: date
    amount: Decimal  # positive magnitude; sign is conveyed by tx_type
    raw_description: str
    tx_type: TxType = TxType.EXPENSE
    status: TransactionStatus = TransactionStatus.COMPLETED
    currency: str = "MXN"


@dataclass
class ParsedStatement:
    source_type: SourceType
    transactions: list[ParsedTransaction] = field(default_factory=list)
    bank: str | None = None
    period_start: date | None = None
    period_end: date | None = None
