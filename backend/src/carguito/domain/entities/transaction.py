from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from ..value_objects.enums import TransactionStatus, TxType

#: Who chose the category. ``auto`` is the ingest classifier's guess; ``user``
#: is a correction, and a correction is never overwritten by a later guess.
CategorySource = Literal["auto", "user"]

#: Who decided ``is_transfer``. Same contract as :data:`CategorySource`: the
#: flag heuristics, the taught-party matcher and the mirror pairing all write
#: ``auto`` and never touch a row marked ``user`` — a human's answer to "is
#: this my own money moving?" outranks every future guess.
TransferSource = Literal["auto", "user"]


@dataclass(slots=True)
class Transaction:
    """A single money movement.

    Sign convention (docs/redesign-plan.md §2): ``amount`` is always a
    **non-negative magnitude** and ``tx_type`` alone carries direction. Sign is
    reintroduced only at aggregation time, via :attr:`signed_amount`.

    A negative ``amount`` is a **parser bug**, so it raises rather than being
    silently ``abs()``-ed. Silent absing is how a negative-signed expense used
    to reach the cube and *subtract* from ``total_expense``.
    """

    user_id: UUID
    tx_date: date
    amount: Decimal
    raw_description: str
    description: str | None = None
    currency: str = "MXN"
    tx_type: TxType = TxType.EXPENSE
    status: TransactionStatus = TransactionStatus.COMPLETED
    statement_id: UUID | None = None
    category_id: UUID | None = None
    merchant_id: UUID | None = None
    category_source: CategorySource = "auto"
    notes: str | None = None
    #: Excluded from every analytics measure by the user's own decision.
    excluded_from_stats: bool = False
    #: Money moving between the user's own accounts (a card payment, a
    #: traspaso). Derived at ingest by ``domain/services/flags.py`` and excluded
    #: by default from every spend measure -- counting a card payment *and* the
    #: card's own charges is the same pesos twice.
    is_transfer: bool = False
    transfer_source: TransferSource = "auto"
    #: Cash out of an ATM. A flag rather than a category, because a
    #: withdrawal's category is genuinely unknown: the statement cannot see
    #: what the cash was spent on.
    is_cash_withdrawal: bool = False
    updated_at: datetime | None = None
    #: The tags attached to this movement. Read-only from the transaction's
    #: point of view -- ``transaction_tags`` is the record of truth and the
    #: repository fills this in -- but carried on the entity so the cube can
    #: denormalise it into ``fact_transactions.tag_ids`` without a second query.
    tag_ids: list[UUID] = field(default_factory=list)
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
        if self.amount < 0:
            raise ValueError(
                f"Transaction.amount must be a non-negative magnitude, got {self.amount}. "
                "Direction belongs in tx_type; a negative amount means the parser "
                "leaked a sign."
            )
        if self.description is None:
            self.description = self.raw_description

    @property
    def signed_amount(self) -> Decimal:
        """``+amount`` for income, ``-amount`` for expense.

        The only place sign is reintroduced. Use this for net figures (cash
        flow, running balances); use :attr:`amount` for directional totals.
        """
        return self.amount if self.tx_type is TxType.INCOME else -self.amount
