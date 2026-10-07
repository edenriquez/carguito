"""Alembic environment.

The database URL is *not* read from alembic.ini. It comes from
``carguito.config.settings.get_settings().database_url`` so that the CLI, the test
suite and ``Container.bootstrap()`` can never disagree about which database
they are pointing at. ``target_metadata`` is
``carguito.adapters.outbound.persistence.models.Base.metadata`` — models.py is the
single source of truth for the schema.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from carguito.adapters.outbound.persistence.models import Base
from carguito.config.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # An explicit -x url=... or a caller-set option wins (used by
    # Container.bootstrap, which already holds a Settings instance).
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A live connection may be handed in by Container.bootstrap() to reuse the
    # engine instead of opening a second one.
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        section = config.get_section(config.config_ini_section, {})
        section["sqlalchemy.url"] = _database_url()
        connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things; batch mode rewrites the table.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
