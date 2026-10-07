from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.entities import Statement
from ...domain.value_objects.enums import AccountKind
from ..ports.outbound import (
    CubeWriter,
    ReceiptRepository,
    StatementRepository,
    TransactionRepository,
)


class StatementNotFoundError(Exception):
    """Raised when a statement does not exist or belongs to another user."""


class UnsetType:
    """Sentinel distinguishing "field absent" from "field explicitly null"."""

    __slots__ = ()


UNSET = UnsetType()


@dataclass(frozen=True)
class DeleteStatementResult:
    statement_id: UUID
    transactions_deleted: int


class ManageStatementsUseCase:
    """Read and delete previously ingested statements.

    Creation lives in :class:`ProcessFileUseCase`; this use case covers the rest
    of the lifecycle. Deleting a statement also removes the transactions derived
    from it -- in the relational store and in the analytics cube -- so the
    dashboards stop counting them. The user's own copy of the raw file lives on
    their phone and is untouched by this.

    Receipts are *detached*, not deleted, by the same operation. A ticket the
    user photographed is their document, and the prices on it are still true
    after the statement that explained the charge goes away; only the link
    between the two dies.
    """

    def __init__(
        self,
        *,
        statements: StatementRepository,
        transactions: TransactionRepository,
        receipts: ReceiptRepository,
        cube: CubeWriter,
    ) -> None:
        self._statements = statements
        self._transactions = transactions
        self._receipts = receipts
        self._cube = cube

    def list(self, *, user_id: UUID) -> list[Statement]:
        return self._statements.list_for_user(user_id)

    def get(self, *, user_id: UUID, statement_id: UUID) -> Statement:
        statement = self._statements.get(statement_id)
        # Treat someone else's statement as missing rather than forbidden, so
        # the response does not disclose that the id exists.
        if statement is None or statement.user_id != user_id:
            raise StatementNotFoundError(str(statement_id))
        return statement

    def update(
        self,
        *,
        user_id: UUID,
        statement_id: UUID,
        kind: AccountKind | None | UnsetType = UNSET,
        bank: str | None | UnsetType = UNSET,
    ) -> Statement:
        """Update the user-editable fields of a statement.

        Two fields and only two: ``account_kind`` (label what kind of account
        this is) and ``bank`` (name the bank when the parser couldn't — the
        generic template stores no bank at all). Period and status stay what
        the parser read; letting the user rewrite those would make an ingest
        bug indistinguishable from an edit. ``UNSET`` means "leave alone",
        ``None`` means "clear" — the distinction the HTTP PATCH contract needs.
        """
        statement = self.get(user_id=user_id, statement_id=statement_id)

        if not isinstance(kind, UnsetType):
            statement.account_kind = kind
        if not isinstance(bank, UnsetType):
            statement.bank = bank
        self._statements.update(statement)
        return statement

    def delete(self, *, user_id: UUID, statement_id: UUID) -> DeleteStatementResult:
        statement = self._statements.get(statement_id)
        # Treat someone else's statement as missing rather than forbidden, so the
        # response does not disclose that the id exists.
        if statement is None or statement.user_id != user_id:
            raise StatementNotFoundError(str(statement_id))

        tx_ids = self._transactions.delete_for_statement(statement_id)
        # Before the rows are gone from anyone else's point of view: a receipt
        # pointing at a deleted movement would render as a ticket attached to
        # nothing, which is worse than one honestly unattached.
        self._receipts.detach_transactions(tx_ids)
        self._statements.delete(statement_id)

        self._cube.delete_transactions(tx_ids)

        return DeleteStatementResult(
            statement_id=statement_id, transactions_deleted=len(tx_ids)
        )
