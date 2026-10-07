from __future__ import annotations

from datetime import date

from collections.abc import Iterator
from typing import Protocol, runtime_checkable
from uuid import UUID

from ....domain.entities import (
    Account,
    Category,
    Conversation,
    ConversationTurn,
    Dashboard,
    DashboardWidget,
    Goal,
    Merchant,
    Receipt,
    Statement,
    Tag,
    Transaction,
    Workstation,
)
from ...dtos.extraction import ParsedTransaction  # noqa: F401  (re-exported convenience)


@runtime_checkable
class TransactionRepository(Protocol):
    def add_many(self, transactions: list[Transaction]) -> None: ...

    def list_for_user(
        self,
        user_id: UUID,
        *,
        start=None,
        end=None,
        category_id: UUID | None = None,
        search: str | None = None,
        statement_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Transaction]: ...

    def count_for_user(self, user_id: UUID, **filters) -> int: ...

    def span_for_user(
        self, user_id: UUID, *, statement_ids: list[UUID] | None = None
    ) -> tuple[date | None, date | None]:
        """``(first, last)`` transaction dates, or ``(None, None)`` for an empty ledger."""
        ...

    def get(self, transaction_id: UUID) -> Transaction | None: ...

    def list_by_ids(self, user_id: UUID, ids: list[UUID]) -> list[Transaction]:
        """Fetch specific transactions, scoped to their owner.

        The scope is the security boundary for bulk operations over
        client-supplied ids: rows the caller does not own simply do not come
        back, so they cannot be acted on.
        """
        ...

    def update(self, transaction: Transaction) -> None:
        """Persist the user-editable fields of an existing transaction.

        Narrow by design: the statement owns date, amount, currency and
        direction, so only description, category (+ its source), notes and the
        stats exclusion travel through here.
        """
        ...

    def delete_for_statement(self, statement_id: UUID) -> list[UUID]:
        """Delete every transaction derived from a statement.

        Returns the ids that were removed so the caller can prune the cube.
        """
        ...

    def iter_for_user(self, user_id: UUID, *, batch_size: int = 500) -> Iterator[Transaction]:
        """Stream **every** transaction for a user, oldest first.

        A separate method rather than `list_for_user(limit=10_000_000)`: a
        magic limit is a silent correctness bug the day someone exceeds it, and
        a full-history read wants to be streamed rather than materialised.
        Used by the cube rebuild.
        """
        ...


@runtime_checkable
class StatementRepository(Protocol):
    def add(self, statement: Statement) -> None: ...

    def update(self, statement: Statement) -> None: ...

    def get(self, statement_id: UUID) -> Statement | None: ...

    def list_for_user(self, user_id: UUID) -> list[Statement]: ...

    def delete(self, statement_id: UUID) -> None: ...

    def exists_hash(self, user_id: UUID, file_hash: str) -> bool: ...


@runtime_checkable
class AccountRepository(Protocol):
    def add(self, account: Account) -> None: ...

    def list_for_user(self, user_id: UUID) -> list[Account]: ...


@runtime_checkable
class GoalRepository(Protocol):
    def add(self, goal: Goal) -> None: ...

    def update(self, goal: Goal) -> None: ...

    def get(self, goal_id: UUID) -> Goal | None: ...

    def list_for_user(self, user_id: UUID) -> list[Goal]: ...

    def delete(self, goal_id: UUID) -> None: ...


@runtime_checkable
class DashboardRepository(Protocol):
    def get_default_for_user(self, user_id: UUID) -> Dashboard | None: ...

    def add(self, dashboard: Dashboard) -> None: ...

    def replace_widgets(self, dashboard_id: UUID, widgets: list[DashboardWidget]) -> None:
        """Swap a dashboard's whole widget list. A layout is saved as a unit."""
        ...


class WorkstationRepository(Protocol):
    """A user's saved lenses. Every read is user-scoped at the query.

    ``get`` takes the user id alongside the workstation id rather than
    filtering afterwards, so a wrong id is a 404 and never someone else's rule.
    """

    def list_for_user(self, user_id: UUID) -> list[Workstation]: ...

    def get(self, user_id: UUID, workstation_id: UUID) -> Workstation | None: ...

    def add(self, workstation: Workstation) -> None: ...

    def replace(self, workstation: Workstation) -> None:
        """Overwrite name, rule and exclusions. A lens is edited as a unit."""
        ...

    def delete(self, user_id: UUID, workstation_id: UUID) -> bool:
        """True when a row was removed, False when there was nothing to remove."""
        ...


class ConversationRepository(Protocol):
    """Chat threads under a workstation, and their messages.

    Same scoping rule as workstations: every read carries the user id in the
    query, so a guessed conversation id is a 404 and never someone else's
    questions about their money.
    """

    def list_for_workstation(
        self, user_id: UUID, workstation_id: UUID
    ) -> list[Conversation]: ...

    def get(self, user_id: UUID, conversation_id: UUID) -> Conversation | None: ...

    def add(self, conversation: Conversation) -> None: ...

    def delete(self, user_id: UUID, conversation_id: UUID) -> bool:
        """Remove the thread and its messages. True when a row was removed."""
        ...

    def delete_for_workstation(self, user_id: UUID, workstation_id: UUID) -> None:
        """A deleted lens takes its conversations with it."""
        ...

    def turns(self, user_id: UUID, conversation_id: UUID) -> list[ConversationTurn]:
        """The thread's messages, oldest first."""
        ...

    def append(self, user_id: UUID, turn: ConversationTurn) -> None:
        """Store one message and bump the conversation's ``updated_at``."""
        ...

    def rename(self, user_id: UUID, conversation: Conversation) -> Conversation | None:
        """Persist a new list title. ``None`` when the thread is not theirs."""
        ...


class DuplicateTagError(ValueError):
    """Two tags with the same slug for one user.

    Declared on the *port* rather than in the adapter: "slugs are unique per
    user" is part of the contract every implementation owes, so the use case
    can name the failure without importing a database module. Subclasses
    ``ValueError`` so an unhandled path still degrades to a 400; the blueprint
    upgrades it to the more precise 409.
    """


@runtime_checkable
class TagRepository(Protocol):
    """Tags plus the ``transaction_tags`` bridge.

    The bridge is the **record of truth** for tagging. The cube's
    ``fact_transactions.tag_ids`` and ``bridge_transaction_tag`` are derived
    copies, rebuildable from here.
    """

    def list_for_user(self, user_id: UUID) -> list[Tag]: ...

    def get(self, tag_id: UUID) -> Tag | None: ...

    def add(self, tag: Tag) -> None: ...

    def update(self, tag: Tag) -> None: ...

    def delete(self, tag_id: UUID) -> None: ...

    def transaction_ids_for_tag(self, tag_id: UUID) -> list[UUID]:
        """Which transactions carry this tag, so their cube rows can be re-derived."""
        ...

    def replace_for_transaction(self, transaction_id: UUID, tag_ids: list[UUID]) -> None:
        """Set one transaction's tag list wholesale."""
        ...

    def attach_to_transactions(self, tag_id: UUID, transaction_ids: list[UUID]) -> None:
        """Add one tag to many transactions without disturbing their other tags."""
        ...


@runtime_checkable
class CategoryRepository(Protocol):
    def get_all(self) -> list[Category]: ...

    def add_many(self, categories: list[Category]) -> None: ...

    def save_many(self, categories: list[Category]) -> None: ...


@runtime_checkable
class MerchantRepository(Protocol):
    def get_all(self) -> list[Merchant]: ...

    def add_many(self, merchants: list[Merchant]) -> None: ...


@runtime_checkable
class UserAliasRepository(Protocol):
    """Per-user display aliases for matching descriptions (migration 0011)."""

    def list_for_user(self, user_id: UUID) -> list[tuple[str, str]]:
        """(label, alias) pairs. Labels arrive already normalized."""
        ...

    def upsert(self, user_id: UUID, label: str, alias: str) -> None:
        """One alias per label: re-teaching replaces."""
        ...


@runtime_checkable
class UserTransferPartyRepository(Protocol):
    """Per-user own-account counterparty names (migration 0016).

    Parties arrive already normalized; this store does not re-normalize.
    """

    def list_for_user(self, user_id: UUID) -> list[str]:
        """Normalized party names, ready for TransferPartyService."""
        ...

    def add(self, user_id: UUID, party: str) -> None:
        """Idempotent: re-teaching the same party is a no-op."""
        ...


@runtime_checkable
class UserLabelRepository(Protocol):
    """Per-user learned categorization vocabulary (migration 0010).

    Labels arrive already normalized; this store does not re-normalize.
    """

    def list_for_user(self, user_id: UUID) -> list[tuple[str, UUID]]:
        """(label, category_id) pairs, ready for CategorizationService."""
        ...

    def add(self, user_id: UUID, category_id: UUID, label: str) -> None:
        """Idempotent: re-teaching the same triple is a no-op."""
        ...


@runtime_checkable
class ReceiptRepository(Protocol):
    """Photographed tickets and their line items, always read together."""

    def add(self, receipt: Receipt) -> None: ...

    def get(self, user_id: UUID, receipt_id: UUID) -> Receipt | None: ...

    def get_for_transaction(self, user_id: UUID, transaction_id: UUID) -> Receipt | None: ...

    def list_for_user(
        self, user_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Receipt]: ...

    def count_for_user(self, user_id: UUID) -> int: ...

    def attached_transaction_ids(self, user_id: UUID) -> set[str]:
        """The movements that already carry a ticket, as one set."""
        ...

    def all_for_user(self, user_id: UUID) -> list[Receipt]:
        """Every receipt, items included. The price comparison's whole input."""
        ...

    def exists_hash(self, user_id: UUID, content_sha256: str) -> bool:
        """Dedup on the phone's digest of the original photo."""
        ...

    def attach(
        self, user_id: UUID, receipt_id: UUID, transaction_id: UUID | None, *, source: str
    ) -> Receipt | None:
        """Point a receipt at a movement, or at nothing. Returns the new state."""
        ...

    def detach_transactions(self, transaction_ids: list[UUID]) -> None:
        """Unpoint receipts whose movement was deleted; keep the receipts."""
        ...

    def delete(self, user_id: UUID, receipt_id: UUID) -> bool: ...
