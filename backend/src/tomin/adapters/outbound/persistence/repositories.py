from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from ....application.ports.outbound.references import ReferenceTerm
from ....application.ports.outbound.repositories import DuplicateTagError
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
    ReceiptItem,
    Statement,
    Tag,
    Transaction,
    Workstation,
    WorkstationRule,
)
from ....domain.value_objects.enums import (
    AccountKind,
    SourceType,
    StatementSource,
    StatementStatus,
    TransactionStatus,
    TxType,
)
from .db import Database
from .models import (
    AccountModel,
    CategoryModel,
    DashboardModel,
    DashboardWidgetModel,
    GoalModel,
    MerchantModel,
    ProductReferenceTermModel,
    UiEventModel,
    ReceiptItemModel,
    ReceiptModel,
    StatementModel,
    TagModel,
    TransactionModel,
    TransactionTagModel,
    UserAliasModel,
    UserCategoryLabelModel,
    UserTransferPartyModel,
    WorkstationChatMessageModel,
    WorkstationConversationModel,
    WorkstationModel,
)


def _u(value) -> str:
    return str(value)


# --- mappers --------------------------------------------------------------
def _tags_by_transaction(session, tx_ids: list[str]) -> dict[str, list[UUID]]:
    """Bridge rows for a *page* of transactions, in one query.

    Loaded in bulk rather than per row: a transaction list is the hottest read
    in the app and an N+1 here would be paid on every scroll.
    """
    if not tx_ids:
        return {}
    rows = session.execute(
        select(TransactionTagModel.transaction_id, TransactionTagModel.tag_id).where(
            TransactionTagModel.transaction_id.in_(tx_ids)
        )
    ).all()
    grouped: dict[str, list[UUID]] = {}
    for tx_id, tag_id in rows:
        grouped.setdefault(tx_id, []).append(UUID(tag_id))
    return grouped


def _tags_for_user(session, user_id: str) -> dict[str, list[UUID]]:
    """Every bridge row a user owns, keyed by transaction.

    Used by the streaming read, where a per-batch lookup would reopen the
    question on every batch. Only *tagged* transactions appear, so this is
    bounded by tagging effort rather than by history size.
    """
    rows = session.execute(
        select(TransactionTagModel.transaction_id, TransactionTagModel.tag_id)
        .join(TagModel, TagModel.id == TransactionTagModel.tag_id)
        .where(TagModel.user_id == user_id)
    ).all()
    grouped: dict[str, list[UUID]] = {}
    for tx_id, tag_id in rows:
        grouped.setdefault(tx_id, []).append(UUID(tag_id))
    return grouped


def _to_transaction(m: TransactionModel, tag_ids: list[UUID] | None = None) -> Transaction:
    return Transaction(
        tag_ids=list(tag_ids or []),
        id=UUID(m.id),
        user_id=UUID(m.user_id),
        statement_id=UUID(m.statement_id) if m.statement_id else None,
        tx_date=m.tx_date,
        amount=Decimal(str(m.amount)),
        raw_description=m.raw_description or "",
        description=m.description,
        currency=m.currency,
        tx_type=TxType(m.tx_type),
        status=TransactionStatus(m.status),
        category_id=UUID(m.category_id) if m.category_id else None,
        merchant_id=UUID(m.merchant_id) if m.merchant_id else None,
        category_source=m.category_source or "auto",
        notes=m.notes,
        excluded_from_stats=bool(m.excluded_from_stats),
        is_transfer=bool(m.is_transfer),
        transfer_source=m.transfer_source or "auto",
        is_cash_withdrawal=bool(m.is_cash_withdrawal),
        updated_at=m.updated_at,
    )



def _to_receipt(m: ReceiptModel, items: list[ReceiptItem]) -> Receipt:
    return Receipt(
        id=UUID(m.id),
        user_id=UUID(m.user_id),
        transaction_id=UUID(m.transaction_id) if m.transaction_id else None,
        store=m.store,
        purchased_at=m.purchased_at,
        purchased_time=m.purchased_time,
        total=Decimal(m.total) if m.total is not None else None,
        currency=m.currency,
        match_source=m.match_source,
        content_sha256=m.content_sha256,
        extractor=m.extractor,
        reader=m.reader,
        captured_at=m.captured_at,
        created_at=m.created_at,
        items=items,
    )


def _to_receipt_item(m: ReceiptItemModel) -> ReceiptItem:
    return ReceiptItem(
        id=UUID(m.id),
        user_id=UUID(m.user_id),
        receipt_id=UUID(m.receipt_id),
        line_no=m.line_no,
        raw_text=m.raw_text,
        description=m.description,
        product_key=m.product_key,
        amount=Decimal(m.amount),
        quantity=Decimal(m.quantity) if m.quantity is not None else None,
        unit_price=Decimal(m.unit_price) if m.unit_price is not None else None,
        size=Decimal(m.size) if m.size is not None else None,
        size_unit=m.size_unit,
    )


def _receipt_model(r: Receipt) -> ReceiptModel:
    return ReceiptModel(
        id=_u(r.id),
        user_id=_u(r.user_id),
        transaction_id=_u(r.transaction_id) if r.transaction_id else None,
        store=r.store,
        purchased_at=r.purchased_at,
        purchased_time=r.purchased_time,
        total=r.total,
        currency=r.currency,
        match_source=r.match_source,
        content_sha256=r.content_sha256,
        extractor=r.extractor,
        reader=r.reader,
        captured_at=r.captured_at,
    )


def _receipt_item_model(i: ReceiptItem) -> ReceiptItemModel:
    return ReceiptItemModel(
        id=_u(i.id),
        user_id=_u(i.user_id),
        receipt_id=_u(i.receipt_id),
        line_no=i.line_no,
        raw_text=i.raw_text,
        description=i.description,
        product_key=i.product_key,
        amount=i.amount,
        quantity=i.quantity,
        unit_price=i.unit_price,
        size=i.size,
        size_unit=i.size_unit,
    )


class SqlTransactionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add_many(self, transactions: list[Transaction]) -> None:
        with self._db.session() as s:
            for t in transactions:
                s.add(
                    TransactionModel(
                        id=_u(t.id),
                        user_id=_u(t.user_id),
                        statement_id=_u(t.statement_id) if t.statement_id else None,
                        tx_date=t.tx_date,
                        raw_description=t.raw_description,
                        description=t.description,
                        amount=t.amount,
                        currency=t.currency,
                        tx_type=t.tx_type.value,
                        status=t.status.value,
                        category_id=_u(t.category_id) if t.category_id else None,
                        merchant_id=_u(t.merchant_id) if t.merchant_id else None,
                        category_source=t.category_source,
                        notes=t.notes,
                        excluded_from_stats=t.excluded_from_stats,
                        is_transfer=t.is_transfer,
                        transfer_source=t.transfer_source,
                        is_cash_withdrawal=t.is_cash_withdrawal,
                    )
                )

    def get(self, transaction_id: UUID) -> Transaction | None:
        with self._db.session() as s:
            m = s.get(TransactionModel, _u(transaction_id))
            if m is None:
                return None
            return _to_transaction(m, _tags_by_transaction(s, [m.id]).get(m.id))

    def list_by_ids(self, user_id: UUID, ids: list[UUID]) -> list[Transaction]:
        """Fetch specific transactions, scoped to their owner.

        The scope is not a convenience: it is what makes a bulk tag operation
        over client-supplied ids unable to touch someone else's rows.
        """
        if not ids:
            return []
        with self._db.session() as s:
            models = list(
                s.scalars(
                    select(TransactionModel).where(
                        TransactionModel.user_id == _u(user_id),
                        TransactionModel.id.in_([_u(i) for i in ids]),
                    )
                ).all()
            )
            tags = _tags_by_transaction(s, [m.id for m in models])
            return [_to_transaction(m, tags.get(m.id)) for m in models]

    def update(self, transaction: Transaction) -> None:
        """Persist the user-editable fields of an already-stored transaction.

        Deliberately narrow: date, amount, currency and ``tx_type`` come from
        the statement and are not the user's to rewrite here. Widening this to
        a blanket "save the entity" would make an ingest bug indistinguishable
        from an edit.
        """
        with self._db.session() as s:
            m = s.get(TransactionModel, _u(transaction.id))
            if m is None:
                return
            m.description = transaction.description
            m.category_id = (
                _u(transaction.category_id) if transaction.category_id else None
            )
            m.category_source = transaction.category_source
            m.notes = transaction.notes
            m.excluded_from_stats = transaction.excluded_from_stats
            # Correctable like the category: the wording heuristics guess at
            # ingest, and taught parties, mirror pairing or the user overturn
            # the guess later. A transfer is never a cash withdrawal, so the
            # pair travels together.
            m.is_transfer = transaction.is_transfer
            m.transfer_source = transaction.transfer_source
            m.is_cash_withdrawal = transaction.is_cash_withdrawal
            m.updated_at = transaction.updated_at

    def _base_query(self, user_id, start, end, category_id, search, statement_ids=None):
        stmt = select(TransactionModel).where(TransactionModel.user_id == _u(user_id))
        if start:
            stmt = stmt.where(TransactionModel.tx_date >= start)
        if end:
            stmt = stmt.where(TransactionModel.tx_date <= end)
        if category_id:
            stmt = stmt.where(TransactionModel.category_id == _u(category_id))
        if search:
            stmt = stmt.where(TransactionModel.description.ilike(f"%{search}%"))
        if statement_ids:
            stmt = stmt.where(
                TransactionModel.statement_id.in_([_u(i) for i in statement_ids])
            )
        return stmt

    def list_for_user(
        self,
        user_id: UUID,
        *,
        start: date | None = None,
        end: date | None = None,
        category_id: UUID | None = None,
        search: str | None = None,
        statement_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Transaction]:
        with self._db.session() as s:
            stmt = (
                self._base_query(user_id, start, end, category_id, search, statement_ids)
                .order_by(TransactionModel.tx_date.desc())
                .limit(limit)
                .offset(offset)
            )
            models = list(s.scalars(stmt).all())
            tags = _tags_by_transaction(s, [m.id for m in models])
            return [_to_transaction(m, tags.get(m.id)) for m in models]

    def iter_for_user(self, user_id: UUID, *, batch_size: int = 500) -> Iterator[Transaction]:
        """Stream a user's entire history, oldest first, in batches.

        ``yield_per`` keeps the result set off the heap; rows are converted to
        detached domain entities as they arrive, so the caller never touches a
        live ORM object.
        """
        with self._db.session() as s:
            stmt = (
                select(TransactionModel)
                .where(TransactionModel.user_id == _u(user_id))
                .order_by(TransactionModel.tx_date, TransactionModel.id)
                .execution_options(yield_per=batch_size)
            )
            # Resolved once for the whole stream: this feeds the cube rebuild,
            # which must reproduce `fact_transactions.tag_ids` exactly.
            tags = _tags_for_user(s, _u(user_id))
            for m in s.scalars(stmt):
                yield _to_transaction(m, tags.get(m.id))

    def count_for_user(self, user_id: UUID, **filters) -> int:
        with self._db.session() as s:
            stmt = self._base_query(
                user_id,
                filters.get("start"),
                filters.get("end"),
                filters.get("category_id"),
                filters.get("search"),
                filters.get("statement_ids"),
            )
            return s.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def span_for_user(
        self, user_id: UUID, *, statement_ids: list[UUID] | None = None
    ) -> tuple[date | None, date | None]:
        """The first and last transaction dates on record.

        The time filter anchors on the *last* one rather than on today: a
        ledger whose newest statement is from June has nothing in "the last 15
        days" of the calendar, and everything in the last 15 days of its own
        history. Same seam as the bank filter (statement ids), so the anchor can
        follow the scope.
        """
        with self._db.session() as s:
            # Aggregate over the *filtered* rows: min/max must read the subquery's
            # own columns, or SQLAlchemy joins the base table back in as a
            # cartesian product and the answer is right only by accident.
            sub = self._base_query(user_id, None, None, None, None, statement_ids).subquery()
            row = s.execute(select(func.min(sub.c.tx_date), func.max(sub.c.tx_date))).one()
            return (row[0], row[1])

    def delete_for_statement(self, statement_id: UUID) -> list[UUID]:
        with self._db.session() as s:
            stmt = select(TransactionModel).where(
                TransactionModel.statement_id == _u(statement_id)
            )
            models = list(s.scalars(stmt).all())
            if models:
                # Explicit rather than relying on ON DELETE CASCADE: SQLite does
                # not enforce foreign keys unless PRAGMA foreign_keys is on, and
                # it is not. Doing it here is correct on both dialects.
                s.execute(
                    delete(TransactionTagModel).where(
                        TransactionTagModel.transaction_id.in_([m.id for m in models])
                    )
                )
            for m in models:
                s.delete(m)
            return [UUID(m.id) for m in models]


class SqlStatementRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, statement: Statement) -> None:
        with self._db.session() as s:
            s.add(self._to_model(statement))

    def update(self, statement: Statement) -> None:
        with self._db.session() as s:
            m = s.get(StatementModel, _u(statement.id))
            if m is None:
                s.add(self._to_model(statement))
            else:
                m.status = statement.status.value
                m.period_start = statement.period_start
                m.period_end = statement.period_end
                m.bank = statement.bank
                m.account_kind = (
                    statement.account_kind.value if statement.account_kind else None
                )
                m.credit_no_interest_payment = statement.credit_no_interest_payment
                m.credit_minimum_payment = statement.credit_minimum_payment
                m.credit_due_date = statement.credit_due_date

    def get(self, statement_id: UUID) -> Statement | None:
        with self._db.session() as s:
            m = s.get(StatementModel, _u(statement_id))
            return self._to_entity(m) if m else None

    def list_for_user(self, user_id: UUID) -> list[Statement]:
        with self._db.session() as s:
            stmt = (
                select(StatementModel)
                .where(StatementModel.user_id == _u(user_id))
                .order_by(StatementModel.uploaded_at.desc())
            )
            return [self._to_entity(m) for m in s.scalars(stmt).all()]

    def delete(self, statement_id: UUID) -> None:
        with self._db.session() as s:
            m = s.get(StatementModel, _u(statement_id))
            if m:
                s.delete(m)

    def exists_hash(self, user_id: UUID, file_hash: str) -> bool:
        with self._db.session() as s:
            stmt = select(StatementModel.id).where(
                StatementModel.user_id == _u(user_id),
                StatementModel.file_hash == file_hash,
            )
            return s.scalar(stmt) is not None

    @staticmethod
    def _to_model(st: Statement) -> StatementModel:
        return StatementModel(
            id=_u(st.id),
            user_id=_u(st.user_id),
            account_id=_u(st.account_id) if st.account_id else None,
            source_type=st.source_type.value,
            bank=st.bank,
            period_start=st.period_start,
            period_end=st.period_end,
            status=st.status.value,
            account_kind=st.account_kind.value if st.account_kind else None,
            credit_no_interest_payment=st.credit_no_interest_payment,
            credit_minimum_payment=st.credit_minimum_payment,
            credit_due_date=st.credit_due_date,
            file_hash=st.file_hash,
            source=st.source.value,
            uploaded_at=st.uploaded_at,
        )

    @staticmethod
    def _to_entity(m: StatementModel) -> Statement:
        return Statement(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            account_id=UUID(m.account_id) if m.account_id else None,
            source_type=SourceType(m.source_type),
            bank=m.bank,
            period_start=m.period_start,
            period_end=m.period_end,
            status=StatementStatus(m.status),
            account_kind=AccountKind(m.account_kind) if m.account_kind else None,
            credit_no_interest_payment=_dec(m.credit_no_interest_payment),
            credit_minimum_payment=_dec(m.credit_minimum_payment),
            credit_due_date=m.credit_due_date,
            file_hash=m.file_hash,
            # `source` is set once at ingest and never edited, so `update()`
            # deliberately leaves it alone.
            source=StatementSource(m.source),
            uploaded_at=m.uploaded_at,
        )


class SqlAccountRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, account: Account) -> None:
        with self._db.session() as s:
            s.add(
                AccountModel(
                    id=_u(account.id),
                    user_id=_u(account.user_id),
                    bank=account.bank,
                    alias=account.alias,
                    account_type=account.account_type,
                )
            )

    def list_for_user(self, user_id: UUID) -> list[Account]:
        with self._db.session() as s:
            stmt = select(AccountModel).where(AccountModel.user_id == _u(user_id))
            return [
                Account(
                    id=UUID(m.id),
                    user_id=UUID(m.user_id),
                    bank=m.bank,
                    alias=m.alias,
                    account_type=m.account_type,
                )
                for m in s.scalars(stmt).all()
            ]


class SqlGoalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, goal: Goal) -> None:
        with self._db.session() as s:
            s.add(self._to_model(goal))

    def update(self, goal: Goal) -> None:
        with self._db.session() as s:
            m = s.get(GoalModel, _u(goal.id))
            if m:
                m.name = goal.name
                m.target_amount = goal.target_amount
                m.current_amount = goal.current_amount
                m.target_date = goal.target_date

    def get(self, goal_id: UUID) -> Goal | None:
        with self._db.session() as s:
            m = s.get(GoalModel, _u(goal_id))
            return self._to_entity(m) if m else None

    def list_for_user(self, user_id: UUID) -> list[Goal]:
        with self._db.session() as s:
            stmt = select(GoalModel).where(GoalModel.user_id == _u(user_id))
            return [self._to_entity(m) for m in s.scalars(stmt).all()]

    def delete(self, goal_id: UUID) -> None:
        with self._db.session() as s:
            m = s.get(GoalModel, _u(goal_id))
            if m:
                s.delete(m)

    @staticmethod
    def _to_model(g: Goal) -> GoalModel:
        return GoalModel(
            id=_u(g.id),
            user_id=_u(g.user_id),
            name=g.name,
            target_amount=g.target_amount,
            current_amount=g.current_amount,
            target_date=g.target_date,
        )

    @staticmethod
    def _to_entity(m: GoalModel) -> Goal:
        return Goal(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            name=m.name,
            target_amount=Decimal(str(m.target_amount)),
            current_amount=Decimal(str(m.current_amount)),
            target_date=m.target_date,
        )


class SqlDashboardRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_default_for_user(self, user_id: UUID) -> Dashboard | None:
        with self._db.session() as s:
            stmt = (
                select(DashboardModel)
                .where(
                    DashboardModel.user_id == _u(user_id),
                    DashboardModel.is_default.is_(True),
                )
                .order_by(DashboardModel.created_at)
            )
            model = s.scalars(stmt).first()
            if model is None:
                return None
            widgets = s.scalars(
                select(DashboardWidgetModel)
                .where(DashboardWidgetModel.dashboard_id == model.id)
                .order_by(DashboardWidgetModel.position)
            ).all()
            return self._to_entity(model, list(widgets))

    def add(self, dashboard: Dashboard) -> None:
        with self._db.session() as s:
            s.add(
                DashboardModel(
                    id=_u(dashboard.id),
                    user_id=_u(dashboard.user_id),
                    name=dashboard.name,
                    is_default=dashboard.is_default,
                )
            )
            s.flush()
            for widget in dashboard.widgets:
                s.add(self._widget_model(dashboard.id, widget))

    def replace_widgets(self, dashboard_id: UUID, widgets: list[DashboardWidget]) -> None:
        """Swap the whole widget list in one transaction.

        A layout is saved as a unit -- reordering, resizing and removing are the
        same gesture in the UI -- so a diff would be more code and more ways to
        end up with two widgets claiming position 3.
        """
        with self._db.session() as s:
            existing = s.scalars(
                select(DashboardWidgetModel).where(
                    DashboardWidgetModel.dashboard_id == _u(dashboard_id)
                )
            ).all()
            for model in existing:
                s.delete(model)
            s.flush()
            for widget in widgets:
                s.add(self._widget_model(dashboard_id, widget))

    @staticmethod
    def _widget_model(dashboard_id: UUID, widget: DashboardWidget) -> DashboardWidgetModel:
        return DashboardWidgetModel(
            id=_u(widget.id),
            dashboard_id=_u(dashboard_id),
            position=widget.position,
            size=widget.size,
            metric_id=widget.metric_id,
            params=dict(widget.params),
            title_override=widget.title_override,
        )

    @staticmethod
    def _to_entity(m: DashboardModel, widgets: list[DashboardWidgetModel]) -> Dashboard:
        return Dashboard(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            name=m.name,
            is_default=bool(m.is_default),
            created_at=m.created_at,
            updated_at=m.updated_at,
            widgets=[
                DashboardWidget(
                    id=UUID(w.id),
                    metric_id=w.metric_id,
                    position=w.position,
                    size=w.size,
                    params=dict(w.params or {}),
                    title_override=w.title_override,
                )
                for w in widgets
            ],
        )


class SqlWorkstationRepository:
    """CRUD for a user's saved lenses.

    Reads are always user-scoped at the query, not filtered after the fact:
    ``get`` takes a user id alongside the workstation id so a wrong id is a
    404 rather than someone else's rule.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_user(self, user_id: UUID) -> list[Workstation]:
        with self._db.session() as s:
            models = s.scalars(
                select(WorkstationModel)
                .where(WorkstationModel.user_id == _u(user_id))
                # Newest first, so the one you just made is at the top of the
                # sidebar. Ties break on `name`, not on `id`: `created_at` has
                # second granularity, a user setting up three lenses in a row
                # lands them all in the same second, and a random-UUID tiebreak
                # would reshuffle the sidebar between reads -- which reads as
                # the app losing track of them. Alphabetical within a second is
                # arbitrary too, but it is *stable*, which is the property that
                # matters for a list you navigate.
                .order_by(WorkstationModel.created_at.desc(), WorkstationModel.name)
            ).all()
            return [self._to_entity(m) for m in models]

    def get(self, user_id: UUID, workstation_id: UUID) -> Workstation | None:
        with self._db.session() as s:
            model = s.scalars(
                select(WorkstationModel).where(
                    WorkstationModel.id == _u(workstation_id),
                    WorkstationModel.user_id == _u(user_id),
                )
            ).first()
            return self._to_entity(model) if model else None

    def add(self, workstation: Workstation) -> None:
        with self._db.session() as s:
            s.add(
                WorkstationModel(
                    id=_u(workstation.id),
                    user_id=_u(workstation.user_id),
                    name=workstation.name,
                    rule=_rule_json(workstation.rule),
                    excluded_tx_ids=[str(i) for i in workstation.excluded_tx_ids],
                )
            )

    def replace(self, workstation: Workstation) -> None:
        """Overwrite name, rule and exclusions in one go.

        A workstation is edited as a unit -- the rule editor saves the whole
        sheet -- so a field-by-field patch would be more code and more ways to
        end up with a name that no longer describes the rule under it.
        """
        with self._db.session() as s:
            model = s.get(WorkstationModel, _u(workstation.id))
            if model is None or model.user_id != _u(workstation.user_id):
                return
            model.name = workstation.name
            model.rule = _rule_json(workstation.rule)
            model.excluded_tx_ids = [str(i) for i in workstation.excluded_tx_ids]

    def delete(self, user_id: UUID, workstation_id: UUID) -> bool:
        with self._db.session() as s:
            model = s.get(WorkstationModel, _u(workstation_id))
            if model is None or model.user_id != _u(user_id):
                return False
            s.delete(model)
            return True

    @staticmethod
    def _to_entity(m: WorkstationModel) -> Workstation:
        raw = dict(m.rule or {})
        return Workstation(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            name=m.name,
            # Rows written before groups existed are flat, and `from_json`
            # reads both shapes -- so an old lens loads as a one-clause rule
            # without a migration touching the JSON column.
            rule=WorkstationRule.from_json(raw),
            excluded_tx_ids=[UUID(i) for i in (m.excluded_tx_ids or [])],
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class SqlConversationRepository:
    """Chat threads under a workstation, and their messages.

    Same discipline as the workstation repo: every read is user-scoped in the
    query itself, so a guessed id is a 404 and never someone else's questions.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_workstation(
        self, user_id: UUID, workstation_id: UUID
    ) -> list[Conversation]:
        with self._db.session() as s:
            models = s.scalars(
                select(WorkstationConversationModel)
                .where(
                    WorkstationConversationModel.user_id == _u(user_id),
                    WorkstationConversationModel.workstation_id == _u(workstation_id),
                )
                # Most recently touched first: the thread you were just in is
                # the one you most likely want back.
                .order_by(
                    WorkstationConversationModel.updated_at.desc(),
                    WorkstationConversationModel.id,
                )
            ).all()
            return [self._to_entity(m) for m in models]

    def get(self, user_id: UUID, conversation_id: UUID) -> Conversation | None:
        with self._db.session() as s:
            model = s.scalars(
                select(WorkstationConversationModel).where(
                    WorkstationConversationModel.id == _u(conversation_id),
                    WorkstationConversationModel.user_id == _u(user_id),
                )
            ).first()
            return self._to_entity(model) if model else None

    def add(self, conversation: Conversation) -> None:
        with self._db.session() as s:
            s.add(
                WorkstationConversationModel(
                    id=_u(conversation.id),
                    user_id=_u(conversation.user_id),
                    workstation_id=_u(conversation.workstation_id),
                    title=conversation.title,
                )
            )

    def delete(self, user_id: UUID, conversation_id: UUID) -> bool:
        with self._db.session() as s:
            model = s.get(WorkstationConversationModel, _u(conversation_id))
            if model is None or model.user_id != _u(user_id):
                return False
            s.execute(
                delete(WorkstationChatMessageModel).where(
                    WorkstationChatMessageModel.conversation_id == _u(conversation_id)
                )
            )
            s.delete(model)
            return True

    def delete_for_workstation(self, user_id: UUID, workstation_id: UUID) -> None:
        with self._db.session() as s:
            ids = s.scalars(
                select(WorkstationConversationModel.id).where(
                    WorkstationConversationModel.user_id == _u(user_id),
                    WorkstationConversationModel.workstation_id == _u(workstation_id),
                )
            ).all()
            if not ids:
                return
            s.execute(
                delete(WorkstationChatMessageModel).where(
                    WorkstationChatMessageModel.conversation_id.in_(ids)
                )
            )
            s.execute(
                delete(WorkstationConversationModel).where(
                    WorkstationConversationModel.id.in_(ids)
                )
            )

    def turns(self, user_id: UUID, conversation_id: UUID) -> list[ConversationTurn]:
        with self._db.session() as s:
            models = s.scalars(
                select(WorkstationChatMessageModel)
                .where(
                    WorkstationChatMessageModel.conversation_id == _u(conversation_id),
                    WorkstationChatMessageModel.user_id == _u(user_id),
                )
                .order_by(WorkstationChatMessageModel.position)
            ).all()
            return [
                ConversationTurn(
                    id=UUID(m.id),
                    conversation_id=UUID(m.conversation_id),
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                )
                for m in models
            ]

    def append(self, user_id: UUID, turn: ConversationTurn) -> None:
        with self._db.session() as s:
            # The ownership check and the position are read inside the same
            # session as the write, so two appends cannot mint one position.
            conversation = s.get(
                WorkstationConversationModel, _u(turn.conversation_id)
            )
            if conversation is None or conversation.user_id != _u(user_id):
                return
            position = s.scalar(
                select(func.count())
                .select_from(WorkstationChatMessageModel)
                .where(
                    WorkstationChatMessageModel.conversation_id
                    == _u(turn.conversation_id)
                )
            )
            s.add(
                WorkstationChatMessageModel(
                    id=_u(turn.id),
                    user_id=_u(user_id),
                    conversation_id=_u(turn.conversation_id),
                    role=turn.role,
                    content=turn.content,
                    position=position or 0,
                )
            )
            # Python time, not func.now(): SQL now() has second granularity on
            # SQLite, and two threads touched in the same second would tie —
            # the picker's "most recent first" needs microseconds to be true.
            conversation.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def rename(self, user_id: UUID, conversation: Conversation) -> Conversation | None:
        with self._db.session() as s:
            model = s.get(WorkstationConversationModel, _u(conversation.id))
            if model is None or model.user_id != _u(user_id):
                return None
            model.title = conversation.title
            return self._to_entity(model)

    @staticmethod
    def _to_entity(m: WorkstationConversationModel) -> Conversation:
        return Conversation(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            workstation_id=UUID(m.workstation_id),
            title=m.title,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


def _rule_json(rule: WorkstationRule) -> dict:
    """The rule as JSON, in the entity's own words.

    Decimals and UUIDs go out as strings: JSON's float would not carry an amount
    bound back unchanged, and a bound that drifts by a centavo silently changes
    which movements are in the set.
    """
    return rule.to_json()


def _uuid_or_none(value) -> UUID | None:
    return UUID(value) if value else None


class SqlCategoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_all(self) -> list[Category]:
        with self._db.session() as s:
            return [
                Category(
                    id=UUID(m.id),
                    name=m.name,
                    color=m.color,
                    icon=m.icon,
                    categorization_labels=list(m.categorization_labels or []),
                    parent_id=UUID(m.parent_id) if m.parent_id else None,
                )
                for m in s.scalars(select(CategoryModel)).all()
            ]

    def add_many(self, categories: list[Category]) -> None:
        with self._db.session() as s:
            for c in categories:
                s.add(
                    CategoryModel(
                        id=_u(c.id),
                        name=c.name,
                        color=c.color,
                        icon=c.icon,
                        categorization_labels=list(c.categorization_labels),
                        parent_id=_u(c.parent_id) if c.parent_id else None,
                    )
                )

    def save_many(self, categories: list[Category]) -> None:
        with self._db.session() as s:
            for c in categories:
                model = s.get(CategoryModel, _u(c.id))
                if model is None:
                    continue
                model.name = c.name
                model.color = c.color
                model.icon = c.icon
                model.categorization_labels = list(c.categorization_labels)
                model.parent_id = _u(c.parent_id) if c.parent_id else None


class SqlUserAliasRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_user(self, user_id: UUID) -> list[tuple[str, str]]:
        with self._db.session() as s:
            stmt = select(UserAliasModel).where(UserAliasModel.user_id == _u(user_id))
            return [(m.label, m.alias) for m in s.scalars(stmt).all()]

    def upsert(self, user_id: UUID, label: str, alias: str) -> None:
        with self._db.session() as s:
            existing = s.scalars(
                select(UserAliasModel).where(
                    UserAliasModel.user_id == _u(user_id),
                    UserAliasModel.label == label,
                )
            ).first()
            if existing:
                existing.alias = alias
                return
            s.add(
                UserAliasModel(
                    id=str(uuid4()), user_id=_u(user_id), label=label, alias=alias
                )
            )


class SqlProductReferenceTermRepository:
    """Which word a product is looked up by, outside this app."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def all_for_user(self, user_id: UUID) -> list[ReferenceTerm]:
        with self._db.session() as s:
            stmt = select(ProductReferenceTermModel).where(
                ProductReferenceTermModel.user_id == _u(user_id)
            )
            return [_term(m) for m in s.scalars(stmt).all()]

    def get(self, user_id: UUID, product_key: str) -> ReferenceTerm | None:
        with self._db.session() as s:
            model = self._row(s, user_id, product_key)
            return _term(model) if model else None

    def upsert(self, user_id: UUID, product_key: str, term: str, source: str) -> None:
        with self._db.session() as s:
            existing = self._row(s, user_id, product_key)
            if existing:
                # A person's answer outranks a model's proposal, always and in
                # one direction. Without this the next automatic lookup would
                # quietly undo every correction the user ever made.
                if existing.source == "user" and source != "user":
                    return
                existing.term = term
                existing.source = source
                existing.updated_at = datetime.now(timezone.utc)
                return
            s.add(
                ProductReferenceTermModel(
                    id=str(uuid4()),
                    user_id=_u(user_id),
                    product_key=product_key,
                    term=term,
                    source=source,
                )
            )

    @staticmethod
    def _row(session, user_id: UUID, product_key: str):
        return session.scalars(
            select(ProductReferenceTermModel).where(
                ProductReferenceTermModel.user_id == _u(user_id),
                ProductReferenceTermModel.product_key == product_key,
            )
        ).first()


def _term(model) -> ReferenceTerm:
    return ReferenceTerm(
        product_key=model.product_key, term=model.term, source=model.source
    )


class SqlUiEventRepository:
    """Interaction events: written in batches, read back as counts."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add_many(self, user_id: UUID, events: list[dict]) -> int:
        with self._db.session() as s:
            for e in events:
                s.add(UiEventModel(
                    id=str(uuid4()), user_id=_u(user_id), name=e["name"], path=e["path"],
                    props=e.get("props") or {}, occurred_at=e["occurred_at"],
                ))
        return len(events)

    def recent(self, user_id: UUID, since: datetime, *, limit: int = 5000) -> list[dict]:
        """Raw events, newest first, for the developer heat view. Capped: the
        view aggregates in the browser, and five thousand rows is a month of
        heavy use, not a year of history."""
        with self._db.session() as s:
            stmt = (
                select(UiEventModel)
                .where(UiEventModel.user_id == _u(user_id), UiEventModel.occurred_at >= since)
                .order_by(UiEventModel.occurred_at.desc())
                .limit(limit)
            )
            return [
                {"name": m.name, "path": m.path, "props": m.props or {},
                 "occurred_at": m.occurred_at.isoformat() + "Z"}
                for m in s.scalars(stmt).all()
            ]

    def summary(self, user_id: UUID, since: datetime) -> list[tuple[str, str, int]]:
        """``(name, path, count)`` rows, most frequent first. The heat map's raw
        material -- what people touch, where."""
        with self._db.session() as s:
            stmt = (
                select(UiEventModel.name, UiEventModel.path, func.count())
                .where(UiEventModel.user_id == _u(user_id), UiEventModel.occurred_at >= since)
                .group_by(UiEventModel.name, UiEventModel.path)
                .order_by(func.count().desc())
            )
            return [(n, p, int(c)) for n, p, c in s.execute(stmt).all()]


class SqlUserTransferPartyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_user(self, user_id: UUID) -> list[str]:
        with self._db.session() as s:
            stmt = select(UserTransferPartyModel).where(
                UserTransferPartyModel.user_id == _u(user_id)
            )
            return [m.party for m in s.scalars(stmt).all()]

    def add(self, user_id: UUID, party: str) -> None:
        with self._db.session() as s:
            existing = s.scalars(
                select(UserTransferPartyModel).where(
                    UserTransferPartyModel.user_id == _u(user_id),
                    UserTransferPartyModel.party == party,
                )
            ).first()
            if existing:
                return
            s.add(
                UserTransferPartyModel(id=str(uuid4()), user_id=_u(user_id), party=party)
            )


class SqlUserLabelRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_user(self, user_id: UUID) -> list[tuple[str, UUID]]:
        with self._db.session() as s:
            stmt = select(UserCategoryLabelModel).where(
                UserCategoryLabelModel.user_id == _u(user_id)
            )
            return [(m.label, UUID(m.category_id)) for m in s.scalars(stmt).all()]

    def add(self, user_id: UUID, category_id: UUID, label: str) -> None:
        with self._db.session() as s:
            exists = s.scalars(
                select(UserCategoryLabelModel).where(
                    UserCategoryLabelModel.user_id == _u(user_id),
                    UserCategoryLabelModel.category_id == _u(category_id),
                    UserCategoryLabelModel.label == label,
                )
            ).first()
            if exists:
                return
            s.add(
                UserCategoryLabelModel(
                    id=str(uuid4()),
                    user_id=_u(user_id),
                    category_id=_u(category_id),
                    label=label,
                )
            )


class SqlTagRepository:
    """Tags and the transaction bridge.

    The bridge lives here rather than on the transaction repository because
    every write to it is a *tagging* operation, and splitting one table's writes
    across two repositories is how the two drift.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_for_user(self, user_id: UUID) -> list[Tag]:
        with self._db.session() as s:
            stmt = (
                select(TagModel)
                .where(TagModel.user_id == _u(user_id))
                .order_by(TagModel.name)
            )
            return [self._to_entity(m) for m in s.scalars(stmt).all()]

    def get(self, tag_id: UUID) -> Tag | None:
        with self._db.session() as s:
            m = s.get(TagModel, _u(tag_id))
            return self._to_entity(m) if m else None

    def add(self, tag: Tag) -> None:
        try:
            with self._db.session() as s:
                s.add(
                    TagModel(
                        id=_u(tag.id),
                        user_id=_u(tag.user_id),
                        name=tag.name,
                        slug=tag.slug,
                        color=tag.color,
                        kind=tag.kind,
                    )
                )
        except IntegrityError as exc:
            # The unique index is the arbiter, not a prior SELECT: a check-then-
            # insert races itself the moment two requests arrive together.
            raise DuplicateTagError(f"Tag '{tag.slug}' already exists.") from exc

    def update(self, tag: Tag) -> None:
        try:
            with self._db.session() as s:
                m = s.get(TagModel, _u(tag.id))
                if m is None:
                    return
                m.name = tag.name
                m.slug = tag.slug
                m.color = tag.color
                m.kind = tag.kind
        except IntegrityError as exc:
            raise DuplicateTagError(f"Tag '{tag.slug}' already exists.") from exc

    def delete(self, tag_id: UUID) -> None:
        with self._db.session() as s:
            # Explicit bridge cleanup: see TransactionTagModel on why the FK's
            # ON DELETE CASCADE cannot be relied on under SQLite.
            s.execute(delete(TransactionTagModel).where(TransactionTagModel.tag_id == _u(tag_id)))
            m = s.get(TagModel, _u(tag_id))
            if m:
                s.delete(m)

    def transaction_ids_for_tag(self, tag_id: UUID) -> list[UUID]:
        """Which transactions carry this tag. Read before a delete, so the cube
        rows that are about to change can be re-derived."""
        with self._db.session() as s:
            rows = s.scalars(
                select(TransactionTagModel.transaction_id).where(
                    TransactionTagModel.tag_id == _u(tag_id)
                )
            ).all()
            return [UUID(r) for r in rows]

    def replace_for_transaction(self, transaction_id: UUID, tag_ids: list[UUID]) -> None:
        """Set a transaction's tag list wholesale.

        Replacement rather than diffing, for the same reason dashboard widgets
        are replaced: the client edits the list as a unit, and a diff is more
        code plus more ways to end up half-applied.
        """
        with self._db.session() as s:
            s.execute(
                delete(TransactionTagModel).where(
                    TransactionTagModel.transaction_id == _u(transaction_id)
                )
            )
            s.flush()
            for tag_id in dict.fromkeys(tag_ids):
                s.add(
                    TransactionTagModel(
                        transaction_id=_u(transaction_id), tag_id=_u(tag_id)
                    )
                )

    def attach_to_transactions(self, tag_id: UUID, transaction_ids: list[UUID]) -> None:
        """Add one tag to many transactions, skipping the ones that have it.

        Additive, not a replacement: bulk-tagging must not silently strip the
        other tags those transactions already carry.
        """
        if not transaction_ids:
            return
        wanted = [_u(i) for i in dict.fromkeys(transaction_ids)]
        with self._db.session() as s:
            existing = set(
                s.scalars(
                    select(TransactionTagModel.transaction_id).where(
                        TransactionTagModel.tag_id == _u(tag_id),
                        TransactionTagModel.transaction_id.in_(wanted),
                    )
                ).all()
            )
            for tx_id in wanted:
                if tx_id not in existing:
                    s.add(TransactionTagModel(transaction_id=tx_id, tag_id=_u(tag_id)))

    @staticmethod
    def _to_entity(m: TagModel) -> Tag:
        return Tag(
            id=UUID(m.id),
            user_id=UUID(m.user_id),
            name=m.name,
            slug=m.slug,
            color=m.color,
            kind=m.kind,
            created_at=m.created_at,
        )


class SqlMerchantRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_all(self) -> list[Merchant]:
        with self._db.session() as s:
            return [
                Merchant(id=UUID(m.id), name=m.name, labels=list(m.labels or []))
                for m in s.scalars(select(MerchantModel)).all()
            ]

    def add_many(self, merchants: list[Merchant]) -> None:
        with self._db.session() as s:
            for m in merchants:
                s.add(MerchantModel(id=_u(m.id), name=m.name, labels=list(m.labels)))


class SqlReceiptRepository:
    """Photographed tickets and their line items.

    Every read is user-scoped in the query itself, so a guessed id is a 404 and
    never someone else's groceries — the same discipline as the workstation and
    conversation repositories.

    Items are always loaded with their receipt. A receipt without its items is
    not a useful object anywhere in this codebase (the detail panel renders
    them, the price book groups them), so lazy loading would only buy the
    chance to forget.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- writes ----------------------------------------------------------
    def add(self, receipt: Receipt) -> None:
        with self._db.session() as s:
            s.add(_receipt_model(receipt))
            for item in receipt.items:
                s.add(_receipt_item_model(item))

    def attach(
        self, user_id: UUID, receipt_id: UUID, transaction_id: UUID | None, *, source: str
    ) -> Receipt | None:
        """Point a receipt at a movement (or at nothing). Returns the new state.

        ``None`` for ``transaction_id`` is a real instruction — "this is not
        that purchase" — and detaching is how a user undoes a wrong automatic
        match.
        """
        with self._db.session() as s:
            model = s.get(ReceiptModel, _u(receipt_id))
            if model is None or model.user_id != _u(user_id):
                return None
            model.transaction_id = _u(transaction_id) if transaction_id else None
            model.match_source = source
            s.flush()
            return self._hydrate(s, [model])[0]

    def detach_transactions(self, transaction_ids: list[UUID]) -> None:
        """Unpoint receipts whose movement no longer exists.

        Called when a statement is deleted. The ticket itself survives: the
        user photographed it, the store did print it, and the price history it
        contributed is still true. Only the link dies.
        """
        if not transaction_ids:
            return
        ids = [_u(i) for i in transaction_ids]
        with self._db.session() as s:
            for model in s.scalars(
                select(ReceiptModel).where(ReceiptModel.transaction_id.in_(ids))
            ).all():
                model.transaction_id = None
                # Back to "auto": the user attached it to a row that is gone,
                # so their answer no longer protects anything from re-matching.
                model.match_source = "auto"

    def delete(self, user_id: UUID, receipt_id: UUID) -> bool:
        with self._db.session() as s:
            model = s.get(ReceiptModel, _u(receipt_id))
            if model is None or model.user_id != _u(user_id):
                return False
            # Explicit, not left to the FK: SQLite does not enforce cascades
            # unless PRAGMA foreign_keys is on, which it is not here.
            s.execute(
                delete(ReceiptItemModel).where(ReceiptItemModel.receipt_id == _u(receipt_id))
            )
            s.delete(model)
            return True

    # --- reads -----------------------------------------------------------
    def exists_hash(self, user_id: UUID, content_sha256: str) -> bool:
        with self._db.session() as s:
            return (
                s.scalar(
                    select(func.count())
                    .select_from(ReceiptModel)
                    .where(
                        ReceiptModel.user_id == _u(user_id),
                        ReceiptModel.content_sha256 == content_sha256,
                    )
                )
                or 0
            ) > 0

    def get(self, user_id: UUID, receipt_id: UUID) -> Receipt | None:
        with self._db.session() as s:
            model = s.scalars(
                select(ReceiptModel).where(
                    ReceiptModel.id == _u(receipt_id),
                    ReceiptModel.user_id == _u(user_id),
                )
            ).first()
            return self._hydrate(s, [model])[0] if model else None

    def attached_transaction_ids(self, user_id: UUID) -> set[str]:
        """The movements that already carry a ticket.

        Read as one set rather than asked per candidate: the matcher considers
        a handful of movements per receipt and a query each would be a join
        done badly, in Python, once per photo.
        """
        with self._db.session() as s:
            return {
                row
                for row in s.scalars(
                    select(ReceiptModel.transaction_id).where(
                        ReceiptModel.user_id == _u(user_id),
                        ReceiptModel.transaction_id.is_not(None),
                    )
                ).all()
                if row
            }

    def get_for_transaction(self, user_id: UUID, transaction_id: UUID) -> Receipt | None:
        with self._db.session() as s:
            model = s.scalars(
                select(ReceiptModel).where(
                    ReceiptModel.transaction_id == _u(transaction_id),
                    ReceiptModel.user_id == _u(user_id),
                )
            ).first()
            return self._hydrate(s, [model])[0] if model else None

    def list_for_user(
        self, user_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Receipt]:
        with self._db.session() as s:
            models = s.scalars(
                select(ReceiptModel)
                .where(ReceiptModel.user_id == _u(user_id))
                # Newest purchase first; an undated ticket sorts by when it was
                # captured rather than disappearing to the bottom forever.
                .order_by(
                    ReceiptModel.purchased_at.desc().nullslast(),
                    ReceiptModel.created_at.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return self._hydrate(s, list(models))

    def count_for_user(self, user_id: UUID) -> int:
        with self._db.session() as s:
            return (
                s.scalar(
                    select(func.count())
                    .select_from(ReceiptModel)
                    .where(ReceiptModel.user_id == _u(user_id))
                )
                or 0
            )

    def all_for_user(self, user_id: UUID) -> list[Receipt]:
        """Every receipt the user owns, items included — the price book's input.

        Unpaginated on purpose, and safe to be: a receipt is one shopping trip,
        so this is bounded by how often a person buys groceries, not by how
        much they spend. The statement path, which *is* unbounded, streams
        instead (``TransactionRepository.iter_for_user``).
        """
        with self._db.session() as s:
            models = s.scalars(
                select(ReceiptModel)
                .where(ReceiptModel.user_id == _u(user_id))
                .order_by(ReceiptModel.purchased_at.desc().nullslast())
            ).all()
            return self._hydrate(s, list(models))

    # --- mapping ---------------------------------------------------------
    def _hydrate(self, session, models: list[ReceiptModel]) -> list[Receipt]:
        """Attach each receipt's items in one extra query, not N."""
        if not models:
            return []
        ids = [m.id for m in models]
        items: dict[str, list[ReceiptItem]] = {}
        for row in session.scalars(
            select(ReceiptItemModel)
            .where(ReceiptItemModel.receipt_id.in_(ids))
            .order_by(ReceiptItemModel.line_no)
        ).all():
            items.setdefault(row.receipt_id, []).append(_to_receipt_item(row))
        return [_to_receipt(m, items.get(m.id, [])) for m in models]


def _dec(value) -> Decimal | None:
    """SQLite hands Numeric back as float on some drivers; the entity wants
    money as Decimal or nothing."""
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
