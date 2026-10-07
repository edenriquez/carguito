"""Re-derive transfer/withdrawal flags: the vocabulary grew (Nu wording).

0008 backfilled the flags with the rule as it stood; the rule has since
learned "su abono" (a card statement acknowledging the payment you made into
it) and "cajita" (Nu's own savings pocket), and learned that a transfer is
never a cash withdrawal. Every stored row must mean the same thing as a row
ingested today, so the whole ledger is re-run through the shared rule —
same reasoning as 0008: the flags are a *classification*, re-derivable from
the description at any time, and one shared implementation in
``domain/services/flags.py`` is the property worth protecting.

Re-flags in BOTH directions (sets and clears), unlike 0008's set-only pass:
this migration's whole point is that some old answers were wrong.

The cube is not touched here — it is derived state; rebuild it
(``POST /api/admin/cube/rebuild``) after upgrading, or the next upload's
rows will disagree with the old ones.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-15
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from carguito.domain.services.flags import detect_flags

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

_transactions = sa.table(
    "transactions",
    sa.column("id", sa.String(36)),
    sa.column("description", sa.String(500)),
    sa.column("raw_description", sa.String(500)),
    sa.column("is_transfer", sa.Boolean()),
    sa.column("is_cash_withdrawal", sa.Boolean()),
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _transactions.c.id,
            _transactions.c.description,
            _transactions.c.raw_description,
            _transactions.c.is_transfer,
            _transactions.c.is_cash_withdrawal,
        )
    ).all()

    changed = 0
    for tx_id, description, raw_description, was_transfer, was_withdrawal in rows:
        flags = detect_flags(raw_description or description)
        if bool(was_transfer) == flags.is_transfer and bool(was_withdrawal) == (
            flags.is_cash_withdrawal
        ):
            continue
        changed += 1
        bind.execute(
            sa.update(_transactions)
            .where(_transactions.c.id == tx_id)
            .values(
                is_transfer=flags.is_transfer,
                is_cash_withdrawal=flags.is_cash_withdrawal,
            )
        )

    logger.info("reflag: %d of %d transactions changed", changed, len(rows))


def downgrade() -> None:
    # The flags are re-derivable; there is nothing meaningful to restore.
    pass
