"""Alembic is the schema's source of transport; models.py its source of truth.

The rest of the suite runs on ``create_all`` for speed, so these are the tests
that keep the two from drifting apart silently.
"""

from __future__ import annotations

from sqlalchemy import inspect

from carguito.adapters.outbound.persistence.db import Database
from carguito.adapters.outbound.persistence.migrator import stamp_head, upgrade_to_head
from carguito.adapters.outbound.persistence.models import Base


def _tables_and_columns(engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        name: {c["name"] for c in inspector.get_columns(name)}
        for name in inspector.get_table_names()
        if name != "alembic_version"
    }


def test_upgrade_head_matches_create_all(tmp_path):
    """A migrated database and a create_all database must be the same shape."""
    migrated = Database(f"sqlite:///{tmp_path / 'migrated.db'}")
    upgrade_to_head(migrated)

    declared = Database(f"sqlite:///{tmp_path / 'declared.db'}")
    declared.create_all()

    assert _tables_and_columns(migrated.engine) == _tables_and_columns(declared.engine)


def test_created_at_columns_exist(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'm.db'}")
    upgrade_to_head(db)
    columns = _tables_and_columns(db.engine)
    for table in ("accounts", "transactions", "goals"):
        assert "created_at" in columns[table], table


def test_stamp_then_upgrade_is_a_noop_for_legacy_databases(tmp_path):
    """A pre-Alembic create_all database can be stamped and then upgraded."""
    db = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(db.engine)

    stamp_head(db)
    upgrade_to_head(db)  # must not try to re-create existing tables

    assert "transactions" in _tables_and_columns(db.engine)
