"""Checkpointer (CLAUDE.md 7.3): ``InMemorySaver`` for ``:memory:`` (tests), SQLite on a file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger("clouddesk.checkpointer")

MEMORY_PATH = ":memory:"
_saver: Any = None
_connection: Any = None


async def get_checkpointer() -> Any:
    """One saver per process, created on first use inside the running event loop."""
    global _saver, _connection
    if _saver is not None:
        return _saver
    path = get_settings().checkpoint_db_path.strip()
    if path in ("", MEMORY_PATH):
        _saver = InMemorySaver()
        return _saver
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _connection = await aiosqlite.connect(path)
    _saver = AsyncSqliteSaver(_connection)
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    """Close the SQLite connection (app shutdown) and forget the saver."""
    global _saver, _connection
    connection, _saver, _connection = _connection, None, None
    if connection is not None:
        try:
            await connection.close()
        except Exception:
            logger.warning("checkpoint connection close failed", exc_info=True)
