from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

#: Who attached the receipt to a movement. ``auto`` is the matcher's guess
#: (same total, same days, same store); ``user`` is a person pointing at the
#: row themselves. Same contract as ``Transaction.category_source``: a
#: correction is never overwritten by a later guess.
MatchSource = Literal["auto", "user"]

#: The base units a size is normalised into. ``pza`` means the ticket named no
#: size at all — a piece is the only thing it can be compared by.
BaseUnit = Literal["l", "kg", "pza"]


@dataclass(slots=True)
class ReceiptItem:
    """One printed line of a ticket: what was bought, and what it cost.

    ``raw_text`` is the record of truth — the OCR line exactly as the phone
    read it. Everything else is derived from it and may be wrong: a ticket is
    a 40-year-old thermal-printer format read through a camera, and the honest
    posture is to keep the evidence next to the interpretation so a reader can
    always check.

    Prices carry two shapes because tickets do. ``amount`` is the line total
    (always present, it is the number that has to add up to the transaction);
    ``unit_price`` is what one of them cost, which is only knowable when the
    ticket printed a quantity or a per-unit price.
    """

    user_id: UUID
    receipt_id: UUID
    line_no: int
    raw_text: str
    description: str
    #: The folded, size-stripped name two tickets are compared *by*. Stored
    #: rather than recomputed at read time for the same reason the transaction
    #: flags are: a change to the normaliser becomes a visible, backfillable
    #: event instead of every historical comparison quietly shifting.
    product_key: str
    amount: Decimal
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    #: The size printed *in the product's name* ("600 ML", "1 KG"), normalised
    #: to :data:`BaseUnit`. ``None`` when the name named no size.
    size: Decimal | None = None
    size_unit: BaseUnit | None = None
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        for name in ("amount", "quantity", "unit_price", "size"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                setattr(self, name, Decimal(str(value)))

    @property
    def each(self) -> Decimal | None:
        """What one of them cost.

        Three cases, in order: the ticket printed a unit price; the ticket
        printed a quantity and the line total, so one costs the quotient; or
        the ticket printed neither, which on every thermal printer in Mexico
        means **one** — a quantity of 1 is the thing they leave out. That last
        reading is a convention, not a guess: it is what the shopper sees, and
        without it three quarters of every basket would be unpriced and the
        comparison would have nothing to compare.
        """
        if self.unit_price is not None:
            return self.unit_price
        if self.quantity is None:
            return self.amount
        if self.quantity > 0:
            return (self.amount / self.quantity).quantize(Decimal("0.01"))
        return None

    @property
    def per_base_unit(self) -> Decimal | None:
        """Price per litre or per kilo, when the name carried a size.

        This is the only figure that compares a 600 ml bottle against a 2 l
        one honestly. It is ``None`` far more often than not, and callers are
        written for that: a comparison that silently fell back to price-per-
        piece across different sizes would be arithmetic nobody asked for.
        """
        each = self.each
        if each is None or self.size is None or self.size <= 0:
            return None
        if self.size_unit not in ("l", "kg"):
            return None
        return (each / self.size).quantize(Decimal("0.01"))


@dataclass(slots=True)
class Receipt:
    """A grocery ticket the user photographed, as structured line items.

    The photo itself is **not here and never was**: the phone reads it on
    device and sends only the text (docs/custody-plan.md G1/G2), exactly like
    a bank statement. ``content_sha256`` is the phone's digest over the
    original image, which is what makes re-sending the same photo the same
    event — the server dedupes on a hash of bytes it has never seen.

    ``transaction_id`` is the whole point of the feature: the ticket is
    *metadata on a movement*. It is nullable because a photo can arrive before
    its statement does, and an unattached receipt is a normal state (the user
    is asked, or a later ingest matches it) rather than a broken one.
    """

    user_id: UUID
    #: The store as printed on the ticket. Not a merchant id: the ticket's own
    #: wording is evidence, and mapping it onto the merchant table is a guess
    #: that belongs to the matcher, not to the record.
    store: str | None = None
    purchased_at: date | None = None
    #: The time of day printed with the date, when the ticket has one.
    purchased_time: time | None = None
    total: Decimal | None = None
    currency: str = "MXN"
    transaction_id: UUID | None = None
    match_source: MatchSource = "auto"
    #: Digest of the original photo, computed on the phone. Dedup key.
    content_sha256: str = ""
    #: Which OCR engine read the image, e.g. ``"mlkit-ios"``. Quality
    #: telemetry, same role as ``ExtractedDocument``'s extractor field.
    extractor: str = "unknown"
    #: Which reader turned lines into items: ``"heuristic"`` or ``"llm:<model>"``.
    #: Stored because the two make different mistakes, and a wrong item list is
    #: much easier to explain when you know who wrote it.
    reader: str = "heuristic"
    captured_at: datetime | None = None
    created_at: datetime | None = None
    items: list[ReceiptItem] = field(default_factory=list)
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        if self.total is not None and not isinstance(self.total, Decimal):
            self.total = Decimal(str(self.total))

    @property
    def items_total(self) -> Decimal:
        """What the line items add up to.

        Compared against :attr:`total` by the UI: when OCR drops a line the two
        disagree, and saying so ("faltan $32.50 respecto al total impreso") is
        better than presenting an incomplete list as if it were the basket.
        """
        return sum((i.amount for i in self.items), Decimal("0"))
