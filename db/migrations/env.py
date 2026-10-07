"""W1 (01-infra-data-impl, task 1.2). Alembic env.

DATABASE_URL (postgresql+asyncpg://…) is the single source of truth.
Migration runs use the sync psycopg2 driver; the async URL form is only
for API/worker runtime code. `alembic check` compares db.models metadata
against the live DB.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Ensure `db.models` is importable when alembic runs from onboarding/.
_HERE = os.path.dirname(os.path.abspath(__file__))  # db/migrations
_DB_DIR = os.path.dirname(_HERE)  # db
_ROOT = os.path.dirname(_DB_DIR)  # onboarding/
for _p in (_ROOT, _DB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return str(config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
