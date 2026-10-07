"""Receipts keep the time of day printed next to the date.

A Mexican ticket stamps ``28/09/26   14:32`` at its foot; the date was read
already, the clock was thrown away. Nullable: most rows ingested before this
column have none, and a ticket can print a date without a time.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.add_column(sa.Column("purchased_time", sa.Time(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.drop_column("purchased_time")
