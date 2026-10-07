"""Async engine / session factory. Postgres (asyncpg) in prod, sqlite (aiosqlite) for dev/tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

_engine = None
_session_factory = None


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def get_engine(url: str | None = None):
    global _engine
    if url is not None:
        return create_async_engine(url, connect_args=_connect_args(url), pool_pre_ping=True)
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL, connect_args=_connect_args(settings.DATABASE_URL), pool_pre_ping=True
        )
    return _engine


def get_session_factory(url: str | None = None):
    global _session_factory
    if url is not None:
        return async_sessionmaker(create_async_engine(url), expire_on_commit=False, class_=AsyncSession)
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def reset_engine_cache() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None
