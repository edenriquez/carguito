from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ...domain.entities import Transaction
from ..ports.outbound import CategoryRepository, CubeWriter, TransactionRepository

#: Sentinel distinguishing "the client did not mention this field" from "the
#: client set it to null". ``category_id: null`` is a real instruction (clear
#: the category); an absent key is not.
UNSET = object()


class TransactionNotFoundError(Exception):
    """Raised when a transaction does not exist or belongs to another user."""


class UnknownCategoryError(ValueError):
    """Raised when the requested category id is not in the category table.

    A ``ValueError`` so the app-wide handler renders it as a 400: this is a bad
    request, not a missing resource -- the *transaction* was found.
    """


class UpdateTransactionUseCase:
    """Apply a user's correction to one transaction.

    The point of the feature is that the user can fix what the ingest
    classifier got wrong, so setting a category here also flips
    ``category_source`` to ``'user'``. That flag is what lets a future
    re-classification pass improve its own guesses without stomping on a human
    decision.

    The cube is written in the same call rather than left to a nightly rebuild.
    A correction that does not move the number on screen reads as a bug, and
    the cube is derived state that can always be re-derived if this write is
    ever lost.
    """

    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        categories: CategoryRepository,
        cube: CubeWriter,
    ) -> None:
        self._transactions = transactions
        self._categories = categories
        self._cube = cube

    def execute(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
        category_id=UNSET,
        description=UNSET,
        notes=UNSET,
        excluded_from_stats=UNSET,
        is_transfer=UNSET,
    ) -> Transaction:
        transaction = self._transactions.get(transaction_id)
        # Someone else's transaction is reported as missing rather than
        # forbidden, so the response does not disclose that the id exists --
        # same non-disclosure pattern as ManageStatementsUseCase.delete.
        if transaction is None or transaction.user_id != user_id:
            raise TransactionNotFoundError(str(transaction_id))

        if category_id is not UNSET:
            if category_id is not None and not self._category_exists(category_id):
                raise UnknownCategoryError(f"Unknown category '{category_id}'.")
            transaction.category_id = category_id
            # The whole reason the column exists.
            transaction.category_source = "user"
        if description is not UNSET:
            transaction.description = description
        if notes is not UNSET:
            transaction.notes = notes
        if excluded_from_stats is not UNSET:
            transaction.excluded_from_stats = bool(excluded_from_stats)
        if is_transfer is not UNSET:
            transaction.is_transfer = bool(is_transfer)
            # A human answered "is this my own money moving?" — the automatic
            # passes (heuristics, taught parties, mirror pairing) must never
            # overturn it in either direction.
            transaction.transfer_source = "user"
            if transaction.is_transfer:
                # Domain rule: a transfer is never a cash withdrawal.
                transaction.is_cash_withdrawal = False

        transaction.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self._transactions.update(transaction)

        # One row, not a rebuild: the edit must be visible in analytics on the
        # next render.
        self._cube.upsert_transactions([transaction])
        return transaction

    def _category_exists(self, category_id: UUID) -> bool:
        return any(c.id == category_id for c in self._categories.get_all())
