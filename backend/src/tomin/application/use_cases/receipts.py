"""Ingesting a photographed ticket, and pointing it at the right movement.

The mirror of ``process_file.py`` for the other half of a purchase. A statement
says *what left the account*; a ticket says *what came home*. This module takes
the lines a phone read off a photo it kept, turns them into products with
comparable prices, and attaches them to the movement they explain.

Everything here is written for the case where the attachment is uncertain,
because it usually is. A receipt whose movement has not been uploaded yet, two
identical charges on the same day, a total the camera read as ``141.6O`` — all
of these end with the ticket stored and unattached, and a question for the
user. None of them end with a guess.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from ...domain.entities import Receipt, ReceiptItem, Transaction
from ...domain.services.products import parse_size, product_key
from ...domain.services.receipt_matching import WINDOW_DAYS, MatchCandidate, match_receipt
from ..dtos.receipts import ParsedReceiptItem
from ..ports.outbound import (
    ReceiptImageOcr,
    ReceiptReader,
    ReceiptRepository,
    TransactionRepository,
)

logger = logging.getLogger(__name__)

#: How many movements around the purchase date the matcher will consider. The
#: window is four days wide; a user with more expenses than this inside it is
#: not going to be helped by a longer list, they are going to be asked.
MAX_CANDIDATES = 200


class DuplicateReceiptError(Exception):
    """This photo was already read (same ``content_sha256``)."""


class ReceiptNotFoundError(Exception):
    """No such receipt, or it belongs to another user."""


class TransactionAlreadyHasReceiptError(Exception):
    """That movement already carries a ticket.

    Reported rather than silently replaced: two tickets on one movement is
    either a mistake worth seeing, or a decision (replace it) that belongs to
    the user.
    """


class UnknownTransactionError(Exception):
    """No such movement, or it belongs to another user."""


class ReceiptOcrUnavailableError(Exception):
    """No OCR engine is installed on this server."""


class NoTextInImageError(Exception):
    """The image decoded, but no text was found on it."""


@dataclass(frozen=True)
class Suggestion:
    """A movement this receipt might belong to, and why."""

    transaction: Transaction
    candidate: MatchCandidate


@dataclass(frozen=True)
class IngestReceiptResult:
    receipt: Receipt
    #: Empty when the receipt attached itself, or when nothing plausible was
    #: found. Non-empty means "the user has to pick".
    suggestions: tuple[Suggestion, ...] = ()


class IngestReceiptUseCase:
    """OCR lines in, a stored basket out.

    The photo is not a parameter and never could be: the phone reads it on
    device and sends text (docs/custody-plan.md G1/G2). ``content_sha256`` is
    the phone's digest of the image, so re-sending the same photo is the same
    event — deduped on a hash of bytes this server has never seen.
    """

    def __init__(
        self,
        *,
        reader: ReceiptReader,
        receipts: ReceiptRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._reader = reader
        self._receipts = receipts
        self._transactions = transactions

    def execute(
        self,
        *,
        user_id: UUID,
        lines: list[str],
        content_sha256: str,
        extractor: str = "unknown",
        captured_at: datetime | None = None,
        transaction_id: UUID | None = None,
    ) -> IngestReceiptResult:
        if self._receipts.exists_hash(user_id, content_sha256):
            raise DuplicateReceiptError(content_sha256)

        parsed = self._reader.read(lines)
        receipt = Receipt(
            user_id=user_id,
            store=parsed.store,
            purchased_at=parsed.purchased_at,
            purchased_time=parsed.purchased_time,
            total=parsed.total,
            currency=parsed.currency,
            content_sha256=content_sha256,
            extractor=extractor,
            reader=parsed.reader,
            captured_at=captured_at,
        )
        receipt.items = [self._to_item(receipt, item) for item in parsed.items]

        suggestions: tuple[Suggestion, ...] = ()
        if transaction_id is not None:
            # The user pointed at a row. That outranks every guess, and it is
            # checked rather than trusted: the id came off the wire.
            self._claim(user_id, transaction_id)
            receipt.transaction_id = transaction_id
            receipt.match_source = "user"
        else:
            matched, candidates = self._match(user_id, receipt)
            if matched is not None:
                receipt.transaction_id = matched
                receipt.match_source = "auto"
            else:
                suggestions = self._suggestions(user_id, candidates)

        self._receipts.add(receipt)
        logger.info(
            "receipt: stored %d item(s) read by %s, %s",
            len(receipt.items),
            receipt.reader,
            "attached" if receipt.transaction_id else "unattached",
        )
        return IngestReceiptResult(receipt=receipt, suggestions=suggestions)

    # --- internals -------------------------------------------------------
    def _to_item(self, receipt: Receipt, parsed: ParsedReceiptItem) -> ReceiptItem:
        size, size_unit = parse_size(parsed.description)
        return ReceiptItem(
            user_id=receipt.user_id,
            receipt_id=receipt.id,
            line_no=parsed.line_no,
            raw_text=parsed.raw_text,
            description=parsed.description,
            # Derived once, at ingest, so every later comparison agrees --
            # the same reasoning as the transaction flags.
            product_key=product_key(parsed.description),
            amount=parsed.amount,
            quantity=parsed.quantity,
            unit_price=parsed.unit_price,
            size=size,
            size_unit=size_unit,
        )

    def _match(
        self, user_id: UUID, receipt: Receipt
    ) -> tuple[UUID | None, list[MatchCandidate]]:
        if receipt.purchased_at is None:
            return (None, [])
        taken = self._receipts.attached_transaction_ids(user_id)
        window = self._window(user_id, receipt.purchased_at)
        # A movement that already carries a ticket is not a candidate: one
        # basket per charge (uq_receipts_transaction says so in the schema).
        free = [t for t in window if str(t.id) not in taken]
        return match_receipt(receipt, free)

    def _window(self, user_id: UUID, purchased_at: date) -> list[Transaction]:
        return self._transactions.list_for_user(
            user_id,
            start=purchased_at - timedelta(days=WINDOW_DAYS),
            end=purchased_at + timedelta(days=WINDOW_DAYS),
            limit=MAX_CANDIDATES,
            offset=0,
        )

    def _suggestions(
        self, user_id: UUID, candidates: list[MatchCandidate]
    ) -> tuple[Suggestion, ...]:
        if not candidates:
            return ()
        found = {
            str(t.id): t
            for t in self._transactions.list_by_ids(
                user_id, [c.transaction_id for c in candidates]
            )
        }
        return tuple(
            Suggestion(transaction=found[str(c.transaction_id)], candidate=c)
            for c in candidates
            if str(c.transaction_id) in found
        )

    def _claim(self, user_id: UUID, transaction_id: UUID) -> None:
        transaction = self._transactions.get(transaction_id)
        if transaction is None or transaction.user_id != user_id:
            raise UnknownTransactionError(str(transaction_id))
        if self._receipts.get_for_transaction(user_id, transaction_id) is not None:
            raise TransactionAlreadyHasReceiptError(str(transaction_id))


class IngestReceiptImageUseCase:
    """A photo in, a stored basket out — the web's way to add a ticket.

    The image is read here and never stored: the OCR sees it in memory, the
    rows go through the same :class:`IngestReceiptUseCase` the phone's text
    does, and the bytes are dropped with the request. ``content_sha256`` is
    computed over the upload so re-sending the same photo is the same event,
    exactly as it is from the phone.
    """

    def __init__(self, *, ocr: ReceiptImageOcr | None, ingest: IngestReceiptUseCase) -> None:
        self._ocr = ocr
        self._ingest = ingest

    @property
    def available(self) -> bool:
        return self._ocr is not None

    def execute(
        self,
        *,
        user_id: UUID,
        image: bytes,
        captured_at: datetime | None = None,
        transaction_id: UUID | None = None,
    ) -> IngestReceiptResult:
        if self._ocr is None:
            raise ReceiptOcrUnavailableError()
        content_sha256 = hashlib.sha256(image).hexdigest()
        lines = self._ocr.read(image)
        if not lines:
            raise NoTextInImageError()
        return self._ingest.execute(
            user_id=user_id,
            lines=lines,
            content_sha256=content_sha256,
            extractor=self._ocr.label,
            captured_at=captured_at,
            transaction_id=transaction_id,
        )


class ManageReceiptsUseCase:
    """Reading, re-attaching and deleting stored tickets."""

    def __init__(
        self,
        *,
        receipts: ReceiptRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._receipts = receipts
        self._transactions = transactions

    def list(self, *, user_id: UUID, limit: int = 100, offset: int = 0):
        return (
            self._receipts.list_for_user(user_id, limit=limit, offset=offset),
            self._receipts.count_for_user(user_id),
        )

    def get(self, *, user_id: UUID, receipt_id: UUID) -> Receipt:
        receipt = self._receipts.get(user_id, receipt_id)
        if receipt is None:
            raise ReceiptNotFoundError(str(receipt_id))
        return receipt

    def for_transaction(self, *, user_id: UUID, transaction_id: UUID) -> Receipt | None:
        return self._receipts.get_for_transaction(user_id, transaction_id)

    def attach(
        self, *, user_id: UUID, receipt_id: UUID, transaction_id: UUID | None
    ) -> Receipt:
        """Point a ticket at a movement, or detach it.

        Always ``match_source="user"``: reaching this method *is* a person
        answering the question, whichever way they answered it, and that answer
        outranks any later automatic match.
        """
        if self._receipts.get(user_id, receipt_id) is None:
            raise ReceiptNotFoundError(str(receipt_id))
        if transaction_id is not None:
            transaction = self._transactions.get(transaction_id)
            if transaction is None or transaction.user_id != user_id:
                raise UnknownTransactionError(str(transaction_id))
            existing = self._receipts.get_for_transaction(user_id, transaction_id)
            if existing is not None and existing.id != receipt_id:
                raise TransactionAlreadyHasReceiptError(str(transaction_id))
        updated = self._receipts.attach(
            user_id, receipt_id, transaction_id, source="user"
        )
        if updated is None:
            raise ReceiptNotFoundError(str(receipt_id))
        return updated

    def delete(self, *, user_id: UUID, receipt_id: UUID) -> None:
        if not self._receipts.delete(user_id, receipt_id):
            raise ReceiptNotFoundError(str(receipt_id))
