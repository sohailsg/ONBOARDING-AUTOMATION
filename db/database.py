"""W1 (01-infra-data-impl): engine/session helpers + DSN handling.

Fail-fast if DSNs are unset (spec 01 §3). Converts between the async
(`postgresql+asyncpg://`, used by API/worker) and sync
(`postgresql+psycopg2://`, used by Alembic online runs, seeds, tests)
forms of DATABASE_URL.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:5432/onboarding"


def get_database_url(sync: bool = False) -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    if not url:
        raise RuntimeError(
            "DATABASE_URL is unset — copy .env.example to .env "
            "(spec 01 §3: fail-fast if unset)."
        )
    if sync:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        if "+asyncpg" in url or url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://")
    return url


def get_redis_url() -> str:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    if not url:
        raise RuntimeError("REDIS_URL is unset — copy .env.example to .env.")
    return url


def create_sync_engine(echo: bool = False) -> Engine:
    return create_engine(get_database_url(sync=True), pool_pre_ping=True)


def create_async_engine_(echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        get_database_url(sync=False), pool_pre_ping=True
    )


SyncSession = sessionmaker(expire_on_commit=False)
