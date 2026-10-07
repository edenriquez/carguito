from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal


@dataclass(frozen=True)
class ParsedReceiptItem:
    """One line a reader believes is a product.

    ``raw_text`` travels all the way to storage: every other field is an
    interpretation of it, and a ticket read through a phone camera earns the
    right to be second-guessed.
    """

    line_no: int
    raw_text: str
    description: str
    amount: Decimal
    quantity: Decimal | None = None
    unit_price: Decimal | None = None


@dataclass(frozen=True)
class ParsedReceipt:
    """What a reader made of the OCR lines, before any of it is persisted.

    Mirrors :class:`~carguito.application.dtos.extraction.ParsedStatement`'s role
    in the statement pipeline: the boundary between "someone read the text" and
    "the application stores facts".
    """

    store: str | None = None
    purchased_at: date | None = None
    #: The clock time printed next to the date, when there is one. Kept apart
    #: from the date because a ticket can carry one without the other.
    purchased_time: time | None = None
    total: Decimal | None = None
    currency: str = "MXN"
    items: list[ParsedReceiptItem] = field(default_factory=list)
    #: Who read the lines: ``"heuristic"`` or ``"llm:<model>"``. Provenance
    #: travels with the parse because the two readers fail differently, and a
    #: basket that came out wrong is far easier to explain when the row itself
    #: says which one wrote it.
    reader: str = "heuristic"
