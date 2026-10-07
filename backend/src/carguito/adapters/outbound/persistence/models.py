from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Time,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false as sa_false,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# UUIDs are stored as 36-char strings for portability across SQLite/Postgres.
UUIDStr = String(36)


def _created_at() -> Mapped[datetime]:
    """`created_at` audit column, matching the Supabase DDL's `timestamptz default now()`."""
    return mapped_column(DateTime, server_default=func.now(), nullable=False)


class CategoryModel(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(60), nullable=True)
    categorization_labels: Mapped[list] = mapped_column(JSON, default=list)
    parent_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("categories.id"), nullable=True, index=True
    )


class MerchantModel(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    labels: Mapped[list] = mapped_column(JSON, default=list)


class AccountModel(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    bank: Mapped[str | None] = mapped_column(String(120), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class StatementModel(Base):
    __tablename__ = "statements"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    account_id: Mapped[str | None] = mapped_column(UUIDStr, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20))
    bank: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # AccountKind value, user-declared via PATCH; NULL until they label it.
    account_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The card figures printed on the statement, when the text carried them.
    credit_no_interest_payment: Mapped[Numeric | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    credit_minimum_payment: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    credit_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # StatementSource value: how the contents reached the server ("web" upload
    # vs "device" on-phone extraction). NOT NULL with a 'web' default, because
    # every row that predates the device path came in through the web one.
    source: Mapped[str] = mapped_column(String(10), server_default="web", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)


class TransactionModel(Base):
    __tablename__ = "transactions"

    # `amount` is always a non-negative magnitude; `tx_type` alone carries
    # direction (see docs/redesign-plan.md §2 "Sign convention").
    __table_args__ = (CheckConstraint("amount >= 0", name="ck_transactions_amount_non_negative"),)

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    statement_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("statements.id"), nullable=True
    )
    tx_date: Mapped[date] = mapped_column(Date, index=True)
    raw_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    tx_type: Mapped[str] = mapped_column(String(10), default="expense")
    status: Mapped[str] = mapped_column(String(12), default="completed")
    category_id: Mapped[str | None] = mapped_column(UUIDStr, nullable=True)
    merchant_id: Mapped[str | None] = mapped_column(UUIDStr, nullable=True)
    # Who decided the category: the ingest classifier ("auto") or the user
    # ("user"). Kept so a future re-classification pass can improve its own
    # guesses without ever overwriting a correction someone made by hand.
    category_source: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="auto", default="auto"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # User-level exclusion from analytics. Distinct from `is_transfer`, which is
    # a derived fact about the movement; this is an opinion about it.
    excluded_from_stats: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    # Derived at ingest from the description (domain/services/flags.py), not
    # user input. Stored rather than recomputed at read time so a heuristic
    # change is a visible, backfillable event instead of every historical
    # number quietly shifting.
    is_transfer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    # Who decided `is_transfer`: the machine ("auto") or the user ("user").
    # Same reasoning as `category_source`: a re-flagging pass — heuristic
    # change, taught party, mirror pairing — must never overwrite a human's
    # answer, and without this column it could not tell the two apart.
    transfer_source: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="auto", default="auto"
    )
    is_cash_withdrawal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    created_at: Mapped[datetime] = _created_at()
    # Nullable rather than defaulted: a row that has never been edited has no
    # meaningful update time, and now() would claim one.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserCategoryLabelModel(Base):
    """A categorization label the user taught the system (see migration 0010).

    Per-user on purpose: categories/merchants are global reference data, and
    one user's "deposito lalo means Ingresos" must not classify anyone else's
    statements. `label` is stored normalized so ingest matching and the unique
    constraint agree about case and accents.
    """

    __tablename__ = "user_category_labels"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category_id", "label", name="uq_user_category_labels_triple"
        ),
    )

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    category_id: Mapped[str] = mapped_column(UUIDStr)
    label: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()


class UserAliasModel(Base):
    """A human name for processor gibberish (see migration 0011).

    `label` is the normalized match text; `alias` is what the user wants to
    read. Applied to `description` at ingest and by the realias bulk pass —
    `raw_description` always keeps the bank's original text.
    """

    __tablename__ = "user_aliases"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_user_aliases_user_label"),)

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    label: Mapped[str] = mapped_column(String(120))
    alias: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created_at()


class UserTransferPartyModel(Base):
    """A counterparty name the user declared as their own (see migration 0016).

    "Eduardo Yael Enriquez Tapia" on a transfer is the user paying themselves,
    but no description-wording rule can know that — the signal is the *name*,
    and only its owner can vouch for it. `party` is stored normalized so
    ingest matching and the unique constraint agree about case and accents.
    """

    __tablename__ = "user_transfer_parties"
    __table_args__ = (
        UniqueConstraint("user_id", "party", name="uq_user_transfer_parties_user_party"),
    )

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    party: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()


class TagModel(Base):
    """A user-defined label. ``slug`` is unique *per user*, not globally.

    Two people may both have a "viaje" tag; one person may not have two.
    """

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_tags_user_slug"),)

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kind: Mapped[str] = mapped_column(
        String(20), server_default="plain", default="plain", nullable=False
    )
    created_at: Mapped[datetime] = _created_at()


class TransactionTagModel(Base):
    """The bridge. A transaction has many tags and a tag has many transactions.

    No surrogate id: the pair *is* the identity, and a composite primary key
    makes "tagged twice with the same tag" unrepresentable rather than merely
    unlikely.

    ``source`` distinguishes a tag the user attached from one a future rule
    engine inferred, so an automatic pass can revise its own work without
    touching a human's.

    ``ondelete="CASCADE"`` guards Postgres. SQLite does not enforce foreign keys
    unless ``PRAGMA foreign_keys`` is on, which it is not here, so the
    repository also deletes bridge rows explicitly -- correct on both dialects.
    """

    __tablename__ = "transaction_tags"

    transaction_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    source: Mapped[str] = mapped_column(
        String(10), server_default="user", default="user", nullable=False
    )
    created_at: Mapped[datetime] = _created_at()


class DashboardModel(Base):
    __tablename__ = "dashboards"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DashboardWidgetModel(Base):
    """A widget row. Owned by its dashboard, and deleted with it.

    ``ondelete="CASCADE"`` rather than an ORM cascade: the layout is replaced
    wholesale on every save, and a widget whose dashboard is gone is not a
    recoverable state worth leaving to application code to remember.
    """

    __tablename__ = "dashboard_widgets"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    dashboard_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    size: Mapped[str] = mapped_column(String(8), default="md")
    metric_id: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    title_override: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ProductReferenceTermModel(Base):
    """What a ticket's shorthand is called out in the world.

    ``GV DETE 7L`` is not a normalisation away from ``detergente``; it is
    knowledge, so it is a row. Keyed by ``product_key`` rather than by receipt
    line: the association belongs to the *product*, and once it is made every
    ticket that ever printed that shorthand inherits it.

    ``source`` is what protects a human's answer from the next guess: a model
    may overwrite its own ``auto`` proposal, never a ``user`` correction.
    """

    __tablename__ = "product_reference_terms"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    product_key: Mapped[str] = mapped_column(String(200))
    term: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(10), default="auto")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint("user_id", "product_key", name="uq_reference_term_product"),
    )


class UiEventModel(Base):
    """One interaction, as the client reported it. Append-only.

    No entity behind it on purpose: an event is a fact about attention, not a
    thing the domain reasons about. When the rows have taught us how people
    work through Movimientos, the *result* of that becomes domain -- a sort
    order, a default view -- and this table stays what it is.
    """

    __tablename__ = "ui_events"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    name: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(String(200))
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = _created_at()


class WorkstationModel(Base):
    """A user's saved lens over the ledger.

    The rule is one JSON column rather than five typed ones. That is a
    deliberate trade: the rule's *shape* is enforced by
    ``domain.entities.WorkstationRule`` and re-validated against the metric
    catalog on every save, so the column never holds something the query layer
    would reject -- and adding a sixth condition stays a domain change instead
    of a migration.
    """

    __tablename__ = "workstations"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    name: Mapped[str] = mapped_column(String(120))
    rule: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Transaction ids the user struck out by hand. Ids rather than a foreign
    #: key: a deleted statement takes its transactions with it, and a stale id
    #: in here is harmless (it excludes a row that no longer exists) while a
    #: cascade would silently rewrite the user's exceptions.
    excluded_tx_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkstationConversationModel(Base):
    """One chat thread under a workstation.

    ``user_id`` is denormalized onto the thread (and onto every message) even
    though the workstation already carries it: it is what lets RLS and every
    query stay owner-scoped without a join, the same property every other
    user-owned table here has.

    No foreign keys, matching ``workstations`` itself: deletion cascades are
    the application's job (``delete_for_workstation``), where they are visible
    in code review instead of hidden in DDL.
    """

    __tablename__ = "workstation_conversations"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    workstation_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()
    #: Bumped on every appended message, so "most recently touched" — the order
    #: the picker lists — is a column read, not a subquery over messages.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class WorkstationChatMessageModel(Base):
    """One stored chat message. Append-only; edits are not a thing chats do."""

    __tablename__ = "workstation_chat_messages"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    conversation_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    #: Explicit order within the thread. ``created_at`` has second granularity
    #: and a question and its answer land in the same second; sorting on time
    #: alone could show an answer above its question.
    position: Mapped[int] = mapped_column(Integer)


class ReceiptModel(Base):
    """A photographed ticket, as structured lines. The photo is not here.

    Deliberately *not* a statement: a statement is the bank's account of what
    left the account, and a receipt is the store's account of what was bought.
    They meet at ``transaction_id``, which is nullable because a ticket can
    arrive before the statement that will explain it — and a receipt with no
    movement yet is a normal state, not an orphan.

    ``content_sha256`` is the phone's digest of the original image. Same column
    meaning as ``statements.file_hash``: re-sending the same photo is the same
    event, deduped on a hash of bytes the server never saw.
    """

    __tablename__ = "receipts"
    __table_args__ = (
        # One movement, one ticket. A second photo of the same purchase is a
        # correction of the first, not a second basket, and the constraint is
        # what stops "total gastado" from being counted twice by any future
        # reader of this table.
        UniqueConstraint("transaction_id", name="uq_receipts_transaction"),
    )

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    transaction_id: Mapped[str | None] = mapped_column(UUIDStr, index=True, nullable=True)
    store: Mapped[str | None] = mapped_column(String(160), nullable=True)
    purchased_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchased_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    total: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="MXN")
    # Who attached it: the matcher ("auto") or the user ("user"). Same contract
    # as `transactions.category_source` — a human's answer is never re-guessed.
    match_source: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="auto", default="auto"
    )
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    # Which OCR engine read the image, and which reader structured the lines.
    # Quality telemetry: a wrong basket is much easier to explain when you know
    # whether a regex or a model wrote it.
    extractor: Mapped[str] = mapped_column(String(40), default="unknown")
    reader: Mapped[str] = mapped_column(String(60), default="heuristic")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ReceiptItemModel(Base):
    """One product line. Owned by its receipt, and deleted with it.

    ``product_key`` is the normalised identity two tickets are compared by
    (``domain/services/products.py``), stored rather than derived at query
    time: the price book groups on it, and a comparison that recomputed the key
    on every read would change its own history the day the normaliser improves.
    """

    __tablename__ = "receipt_items"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    receipt_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("receipts.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    # The OCR line exactly as the phone read it: the evidence behind every
    # other column on this row.
    raw_text: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(String(200))
    product_key: Mapped[str] = mapped_column(String(200), index=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))
    quantity: Mapped[Numeric | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit_price: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)
    # The size printed in the name, normalised to litres or kilos. NULL is the
    # common case (anything sold loose) and means "compare by piece".
    size: Mapped[Numeric | None] = mapped_column(Numeric(12, 4), nullable=True)
    size_unit: Mapped[str | None] = mapped_column(String(4), nullable=True)


class GoalModel(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(UUIDStr, primary_key=True)
    user_id: Mapped[str] = mapped_column(UUIDStr, index=True)
    name: Mapped[str] = mapped_column(String(160))
    target_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))
    current_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), default=0)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = _created_at()
