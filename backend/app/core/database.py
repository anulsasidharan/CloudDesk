"""Async SQLAlchemy engine and sessions (SQLite for the demo, Postgres in the cloud).

Engines are cached per ``DATABASE_URL`` and disposed at shutdown. Repositories receive an
``AsyncSession``; they never open one themselves.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engines: dict[str, AsyncEngine] = {}


def database_configured() -> bool:
    """True when ``DATABASE_URL`` is set. Performs no I/O."""
    return bool(get_settings().database_url.strip())


def enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores foreign keys unless asked; turn them on so it behaves like Postgres."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> AsyncEngine:
    url = get_settings().database_url.strip()
    engine = _engines.get(url)
    if engine is None:
        engine = create_async_engine(url, future=True)
        enable_sqlite_foreign_keys(engine)
        _engines[url] = engine
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """One unit of work: commit on success, roll back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that commits when the request succeeds."""
    async with session_scope() as session:
        yield session


def _ensure_sqlite_directory(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


async def create_tables() -> None:
    """Create any missing tables. Intended for the SQLite demo; Postgres uses ``database/``."""
    from app.models import entities  # noqa: F401  (registers tables on the metadata)
    from app.models.base import Base

    _ensure_sqlite_directory(get_settings().database_url.strip())
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    engines = list(_engines.values())
    _engines.clear()
    for engine in engines:
        await engine.dispose()
