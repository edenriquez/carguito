"""Programmatic Alembic driver.

``Container.bootstrap()`` calls :func:`upgrade_to_head` instead of
``create_all()``. Running the migrations in-process keeps schema evolution on
the same code path as the app: there is no "remember to run alembic" step that
a deploy can skip.

The live SQLAlchemy connection is handed to ``env.py`` via
``config.attributes`` so the migration runs on the engine the app already owns,
rather than opening a second connection from a re-parsed URL.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .db import Database

logger = logging.getLogger(__name__)


def _alembic_config_path() -> Path:
    """Locate ``backend/alembic.ini`` relative to this module."""
    # .../backend/src/tomin/adapters/outbound/persistence/migrator.py
    backend_root = Path(__file__).resolve().parents[5]
    path = backend_root / "alembic.ini"
    if not path.is_file():
        raise FileNotFoundError(
            f"alembic.ini not found at {path}. Migrations can only run from a source "
            "checkout; set run_migrations=false and manage the schema out of band."
        )
    return path


def build_config(database_url: str | None = None) -> Config:
    path = _alembic_config_path()
    config = Config(str(path))
    config.set_main_option("script_location", str(path.parent / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


#: Revision 0001 reproduces exactly what the pre-Alembic ``create_all()`` made.
BASELINE_REVISION = "0001"


def _is_unversioned_legacy_database(db: Database) -> bool:
    """True for a database built by ``create_all`` before Alembic existed.

    Such a database already holds the baseline tables but has no
    ``alembic_version`` row, so ``upgrade`` would try to CREATE TABLE over them.
    """
    names = set(inspect(db.engine).get_table_names())
    if "transactions" not in names:
        return False
    if "alembic_version" not in names:
        return True
    # An empty alembic_version means the same thing: nothing has been applied.
    with db.engine.connect() as connection:
        return connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar() == 0


def upgrade_to_head(db: Database, database_url: str | None = None) -> None:
    """Run ``alembic upgrade head`` against ``db``'s engine.

    A legacy ``create_all`` database is stamped at the baseline first, so the
    transition needs no manual step (see backend/README.md).
    """
    config = build_config(database_url)

    if _is_unversioned_legacy_database(db):
        logger.warning(
            "Database has the baseline tables but no alembic_version; "
            "stamping revision %s before upgrading.",
            BASELINE_REVISION,
        )
        _run(config, db, command.stamp, BASELINE_REVISION)

    _run(config, db, command.upgrade, "head")
    logger.info("Database schema is at Alembic head.")


def stamp_head(db: Database, database_url: str | None = None) -> None:
    """Mark ``db`` as being at head without running any migration."""
    _run(build_config(database_url), db, command.stamp, "head")


def _run(config: Config, db: Database, action, revision: str) -> None:
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        action(config, revision)
