from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from ..value_objects.enums import (
    AccountKind,
    SourceType,
    StatementSource,
    StatementStatus,
)


@dataclass(slots=True)
class Statement:
    user_id: UUID
    source_type: SourceType
    bank: str | None = None
    account_id: UUID | None = None
    period_start: date | None = None
    period_end: date | None = None
    status: StatementStatus = StatementStatus.PENDING
    # User-declared account kind (see AccountKind). None = not yet labelled.
    account_kind: AccountKind | None = None
    # What a card statement asks to be paid, read off its text at ingest
    # (see domain/services/credit_summary.py). All None for a debit statement,
    # and for a card statement whose figures the reader could not find.
    credit_no_interest_payment: Decimal | None = None
    credit_minimum_payment: Decimal | None = None
    credit_due_date: date | None = None
    file_hash: str | None = None
    # How the contents got here. Defaults to WEB because that is the path that
    # existed first and every stored row predates the device one.
    source: StatementSource = StatementSource.WEB
    uploaded_at: datetime = None  # type: ignore[assignment]
    id: UUID = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()
        if self.uploaded_at is None:
            self.uploaded_at = datetime.now(timezone.utc)

    def mark(self, status: StatementStatus) -> None:
        self.status = status
