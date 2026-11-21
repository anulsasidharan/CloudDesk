"""Shared pieces for tools: the result type and the single database-session seam."""

from contextlib import asynccontextmanager
from typing import Any, Literal

from pydantic import BaseModel

from app.core import database

ToolStatus = Literal["ok", "approval_required", "error", "timeout", "unknown_tool"]


class ToolResult(BaseModel):
    """What every tool call returns. Tool failures are data, never exceptions."""

    tool: str
    ok: bool
    status: ToolStatus
    requires_approval: bool = False
    executed: bool = False
    data: dict[str, Any] | None = None
    error: str | None = None


@asynccontextmanager
async def tool_session():
    """One unit of work for a tool. Tests replace this to point at a private database."""
    async with database.session_scope() as session:
        yield session
