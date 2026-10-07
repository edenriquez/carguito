from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

import duckdb

from ....application.dtos.analytics import (
    CategorySpend,
    MonthlyPoint,
    SpendingSummary,
)
from ....domain.entities import Category, Tag, Transaction

#: Aggregates are scoped to a single currency. Everything the app ingests today
#: is Mexican, so MXN is the default rather than a required argument.
DEFAULT_CURRENCY = "MXN"

_UPSERT_FACT = (
    "INSERT OR REPLACE INTO fact_transactions VALUES "
    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

#: Bump whenever the cube table shapes change. The cube is derived state with
#: no migrations: an on-disk file created by an older build simply gets its
#: tables dropped and recreated, then repopulated from the relational store.
#: Without this, ``CREATE TABLE IF NOT EXISTS`` silently keeps the old shape
#: and every metric that references a new column fails at read time.
_SCHEMA_VERSION = 3


class DuckDbCube:
    """DuckDB-backed analytics cube (implements CubeWriter + CubeReader).

    Structured transactions are streamed into ``fact_transactions`` as they are
    processed, and every read aggregates that one fact table directly.

    There are deliberately **no rollup tables**. The previous ``rollup_monthly``
    and ``rollup_category`` were written on every upload and every delete and
    then never read by anything; ``refresh_rollups`` also ignored its
    ``user_id`` argument and rebuilt every user's rollups each time. They have
    been deleted rather than fixed. If aggregate reads ever become slow enough
    to matter, a materialisation should be added back with a reader that
    actually consults it.

    The cube is derived state. :meth:`rebuild_for_user` reconstructs it from
    the relational tables, which is what makes it safe to throw away.

    DuckDB allows a single writer per file, so the connection is opened lazily on
    first use rather than in ``__init__``. Importing the app therefore does not
    take the file lock -- which matters under the Flask dev reloader, where the
    parent process imports the app but never serves a request.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._lock = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None

    @property
    def _connection(self) -> duckdb.DuckDBPyConnection:
        """Connection, opened on first access. Callers must hold ``self._lock``."""
        if self._con is None:
            self._con = duckdb.connect(self._path)
            self._create_schema()
        return self._con

    def _create_schema(self) -> None:
        assert self._con is not None
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS cube_meta (key VARCHAR PRIMARY KEY, value INTEGER);"
        )
        row = self._con.execute(
            "SELECT value FROM cube_meta WHERE key = 'schema_version'"
        ).fetchone()
        has_facts = (
            self._con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'fact_transactions'"
            ).fetchone()[0]
            > 0
        )
        # No recorded version but a facts table present = a file from before
        # cube_meta existed; its shape is unknowable, so treat it as stale.
        if has_facts and (row is None or row[0] != _SCHEMA_VERSION):
            # Stale shape from an older build. Derived state: drop and let the
            # CREATEs below rebuild the shape. Facts are gone until someone
            # repopulates (upload, or POST /api/admin/cube/rebuild) — an empty
            # correct answer beats a binder error on every metric.
            self._con.execute("DROP TABLE IF EXISTS fact_transactions;")
            self._con.execute("DROP TABLE IF EXISTS bridge_transaction_tag;")
            self._con.execute("DROP TABLE IF EXISTS dim_tag;")
            self._con.execute("DROP TABLE IF EXISTS dim_category;")
        self._con.execute(
            "INSERT OR REPLACE INTO cube_meta VALUES ('schema_version', ?)",
            [_SCHEMA_VERSION],
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_transactions (
                tx_id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                tx_date DATE,
                amount DECIMAL(14,2),
                currency VARCHAR,
                tx_type VARCHAR,
                category_id VARCHAR,
                merchant_id VARCHAR,
                description VARCHAR,
                excluded_from_stats BOOLEAN,
                is_transfer BOOLEAN,
                is_cash_withdrawal BOOLEAN,
                tag_ids VARCHAR[],
                -- The statement the row came from: the seam every
                -- account-scoped filter (bank, card) reaches through.
                statement_id VARCHAR
            );
            """
        )
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS dim_category "
            "(category_id VARCHAR PRIMARY KEY, name VARCHAR);"
        )
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS dim_tag (tag_id VARCHAR PRIMARY KEY, name VARCHAR);"
        )
        # Tags go into the cube **both ways** (docs/redesign-plan.md §7). The
        # array column answers "is this transaction tagged X" with
        # `list_contains` and no join; the bridge answers "total per tag", which
        # needs one row per (transaction, tag) pair. Neither one does the other's
        # job well, and both are derived from `transaction_tags`.
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS bridge_transaction_tag "
            "(tx_id VARCHAR, tag_id VARCHAR, PRIMARY KEY (tx_id, tag_id));"
        )

    # --- writer ----------------------------------------------------------
    def sync_categories(self, categories: list[Category]) -> None:
        with self._lock:
            for c in categories:
                self._connection.execute(
                    "INSERT OR REPLACE INTO dim_category VALUES (?, ?)",
                    [str(c.id), c.name],
                )

    def sync_tags(self, tags: list[Tag]) -> None:
        """Refresh the tag dimension so a tag breakdown has labels to show.

        Mirrors :meth:`sync_categories`. Deleted tags are pruned rather than
        left behind: a stale label attached to no facts is invisible, but a
        stale label reattached by an id reused elsewhere is a wrong answer.
        """
        with self._lock:
            for t in tags:
                self._connection.execute(
                    "INSERT OR REPLACE INTO dim_tag VALUES (?, ?)", [str(t.id), t.name]
                )

    def forget_tag(self, tag_id: UUID) -> None:
        """Drop a deleted tag's dimension row and every bridge row it owned."""
        with self._lock:
            self._connection.execute(
                "DELETE FROM bridge_transaction_tag WHERE tag_id = ?", [str(tag_id)]
            )
            self._connection.execute("DELETE FROM dim_tag WHERE tag_id = ?", [str(tag_id)])

    def upsert_transactions(self, transactions: list[Transaction]) -> None:
        if not transactions:
            return
        with self._lock:
            for t in transactions:
                self._connection.execute(_UPSERT_FACT, self._fact_row(t))
                self._write_bridge(t)

    def _write_bridge(self, t: Transaction) -> None:
        """Re-derive one transaction's bridge rows. Callers hold ``self._lock``.

        Delete-then-insert rather than insert-if-missing: the entity's tag list
        is the whole truth for that transaction, so untagging has to be able to
        remove a row, not just fail to add one.
        """
        assert self._con is not None
        self._con.execute("DELETE FROM bridge_transaction_tag WHERE tx_id = ?", [str(t.id)])
        for tag_id in t.tag_ids:
            self._con.execute(
                "INSERT OR REPLACE INTO bridge_transaction_tag VALUES (?, ?)",
                [str(t.id), str(tag_id)],
            )

    def delete_transactions(self, tx_ids: list[UUID]) -> None:
        if not tx_ids:
            return
        placeholders = ", ".join("?" * len(tx_ids))
        ids = [str(i) for i in tx_ids]
        with self._lock:
            self._connection.execute(
                f"DELETE FROM bridge_transaction_tag WHERE tx_id IN ({placeholders})", ids
            )
            self._connection.execute(
                f"DELETE FROM fact_transactions WHERE tx_id IN ({placeholders})", ids
            )

    def rebuild_for_user(self, user_id: UUID, transactions: Iterable[Transaction]) -> int:
        """Discard and re-derive one user's fact rows. Returns the row count.

        The cube is a *derived* store: the relational tables are the record of
        truth and this can always reconstruct it. That is what makes DuckDB
        replaceable — and what makes every later backfill (transfer flags,
        fingerprints, tags) a rebuild rather than a bespoke migration.

        Delete and repopulate happen under one lock so a concurrent read never
        observes a user with no transactions. ``transactions`` is supplied by
        the caller rather than fetched here: the cube adapter must not reach
        for a repository.
        """
        with self._lock:
            # Bridge rows first, while the fact table still says which
            # transactions are this user's -- the bridge carries no user_id, by
            # the same reasoning as the relational one.
            self._connection.execute(
                "DELETE FROM bridge_transaction_tag WHERE tx_id IN "
                "(SELECT tx_id FROM fact_transactions WHERE user_id = ?)",
                [str(user_id)],
            )
            self._connection.execute(
                "DELETE FROM fact_transactions WHERE user_id = ?", [str(user_id)]
            )
            count = 0
            for t in transactions:
                self._connection.execute(_UPSERT_FACT, self._fact_row(t))
                self._write_bridge(t)
                count += 1
        return count

    @staticmethod
    def _fact_row(t: Transaction) -> list:
        return [
            str(t.id),
            str(t.user_id),
            t.tx_date,
            t.amount,
            t.currency,
            t.tx_type.value,
            str(t.category_id) if t.category_id else None,
            str(t.merchant_id) if t.merchant_id else None,
            t.description or t.raw_description,
            t.excluded_from_stats,
            t.is_transfer,
            t.is_cash_withdrawal,
            [str(tag_id) for tag_id in t.tag_ids],
            str(t.statement_id) if t.statement_id else None,
        ]

    # --- reader ----------------------------------------------------------
    def fetch(self, sql: str, params: list) -> list[tuple]:
        """Run one read against the fact tables under this cube's lock.

        Exposed for the sibling adapter in this package: the metric engine
        compiles its own SQL, and DuckDB is single-writer, so every statement
        has to travel through the one connection this class owns rather than a
        second one opened on the same file.

        ``sql`` is built from whitelisted identifiers by the caller; ``params``
        carries every value. Nothing user-supplied is ever interpolated.
        """
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def spending_by_category(
        self,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        currency: str = DEFAULT_CURRENCY,
    ) -> list[CategorySpend]:
        clause, params = self._filter(user_id, start, end, currency)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT f.category_id,
                       COALESCE(d.name, 'Sin Categoria') AS name,
                       SUM(f.amount) AS total
                FROM fact_transactions f
                LEFT JOIN dim_category d ON f.category_id = d.category_id
                WHERE f.tx_type = 'expense' {clause}
                GROUP BY f.category_id, name
                ORDER BY total DESC
                """,
                params,
            ).fetchall()
        total = sum((r[2] for r in rows), Decimal(0)) or Decimal(1)
        return [
            CategorySpend(
                category_id=r[0],
                category_name=r[1],
                amount=Decimal(str(r[2])),
                percentage=round(float(r[2]) / float(total) * 100, 1),
            )
            for r in rows
        ]

    def monthly_series(self, user_id: UUID, months: int = 12) -> list[MonthlyPoint]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT strftime(tx_date, '%Y-%m') AS month,
                       SUM(CASE WHEN tx_type = 'income' THEN amount ELSE 0 END) AS income,
                       SUM(CASE WHEN tx_type = 'expense' THEN amount ELSE 0 END) AS expense
                FROM fact_transactions
                WHERE user_id = ?
                GROUP BY month
                ORDER BY month DESC
                LIMIT ?
                """,
                [str(user_id), months],
            ).fetchall()
        points = [
            MonthlyPoint(month=r[0], income=Decimal(str(r[1])), expense=Decimal(str(r[2])))
            for r in rows
        ]
        points.reverse()
        return points

    def spending_summary(
        self,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        currency: str = DEFAULT_CURRENCY,
    ) -> SpendingSummary:
        clause, params = self._filter(user_id, start, end, currency)
        with self._lock:
            income, expense = self._connection.execute(
                f"""
                SELECT
                    SUM(CASE WHEN tx_type = 'income' THEN amount ELSE 0 END),
                    SUM(CASE WHEN tx_type = 'expense' THEN amount ELSE 0 END)
                FROM fact_transactions f
                WHERE 1=1 {clause}
                """,
                params,
            ).fetchone()

        by_category = self.spending_by_category(user_id, start, end, currency)
        monthly = self.monthly_series(user_id)
        return SpendingSummary(
            total_income=Decimal(str(income or 0)),
            total_expense=Decimal(str(expense or 0)),
            top_category=by_category[0].category_name if by_category else None,
            by_category=by_category,
            monthly=monthly,
        )

    @staticmethod
    def _filter(
        user_id: UUID,
        start: date | None,
        end: date | None,
        currency: str | None = DEFAULT_CURRENCY,
    ):
        clause = "AND f.user_id = ?"
        params: list = [str(user_id)]
        if currency:
            # Money in different currencies does not add up. Summing MXN and
            # USD produced a headline number in no currency at all, so every
            # aggregate is scoped to exactly one.
            clause += " AND f.currency = ?"
            params.append(currency)
        if start:
            clause += " AND f.tx_date >= ?"
            params.append(start)
        if end:
            clause += " AND f.tx_date <= ?"
            params.append(end)
        return clause, params
