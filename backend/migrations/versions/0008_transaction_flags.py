"""Transfer + cash-withdrawal flags, with a data backfill (B7).

Metrics 4 and 9, and every other number gets more correct (§7). Two derived
booleans on ``transactions``, plus a backfill so existing history means the same
thing as anything uploaded after this.

**Why the backfill imports the domain rule instead of inlining SQL LIKEs.**
Freezing a copy of the heuristic in this file is the usual migration
discipline, and it is wrong here. These flags are a *classification*: if the
backfill classifies "PAGO TC BBVA" differently from ingest, the database ends
up in a state where the same description means two different things depending
on when it was uploaded, and no later rebuild can tell which rows are which.
One shared rule in ``domain/services/flags.py`` is the property worth
protecting; a stale-migration replay is not, because the flags are re-derivable
from the description at any time.

Row-by-row Python is affordable at this scale (a personal-finance history is
thousands of rows, not billions) and it is the only way to run exactly the
ingest rule, accent folding and fee exclusion included.

The cube is **not** touched. It is derived state and `rebuild_for_user` is the
supported way to pick these columns up (§7, B2) -- which is the whole reason the
cube was made disposable before this step.

Adds no table, so no new RLS policy: ``transactions`` is already covered by 0003.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-28
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from carguito.domain.services.flags import detect_flags

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

_COLUMNS = ("is_transfer", "is_cash_withdrawal")

_transactions = sa.table(
    "transactions",
    sa.column("id", sa.String(36)),
    sa.column("description", sa.String(500)),
    sa.column("raw_description", sa.String(500)),
    sa.column("is_transfer", sa.Boolean()),
    sa.column("is_cash_withdrawal", sa.Boolean()),
)


def upgrade() -> None:
    # batch_alter_table: SQLite cannot add a NOT NULL column to a populated
    # table without rebuilding it. On PostgreSQL this degrades to a plain
    # ALTER. Same reasoning as 0002.
    with op.batch_alter_table("transactions") as batch:
        for name in _COLUMNS:
            batch.add_column(
                sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false())
            )

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _transactions.c.id, _transactions.c.description, _transactions.c.raw_description
        )
    ).all()

    transfers = withdrawals = 0
    for tx_id, description, raw_description in rows:
        flags = detect_flags(description or raw_description)
        if not (flags.is_transfer or flags.is_cash_withdrawal):
            continue
        transfers += flags.is_transfer
        withdrawals += flags.is_cash_withdrawal
        bind.execute(
            sa.update(_transactions)
            .where(_transactions.c.id == tx_id)
            .values(
                is_transfer=flags.is_transfer,
                is_cash_withdrawal=flags.is_cash_withdrawal,
            )
        )

    # Logged rather than silent, in the spirit of B1's sign backfill: how many
    # rows were wrong is the interesting part of a correctness fix.
    logger.info(
        "Flag backfill over %s transaction(s): %s transfer(s), %s cash withdrawal(s).",
        len(rows),
        transfers,
        withdrawals,
    )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        for name in reversed(_COLUMNS):
            batch.drop_column(name)
