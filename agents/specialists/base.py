"""Shared pieces for the six specialists: result envelope and the one way to run a tool."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from app.schemas.workflow import TokenUsage, ToolCallRecord
from app.tools import ToolRegistry, ToolResult, get_registry

T = TypeVar("T")


@dataclass
class AgentResult(Generic[T]):
    """What a specialist hands back to its graph node: output plus what the tracer records."""

    output: T
    usage: TokenUsage = field(default_factory=TokenUsage)
    duration_ms: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


async def run_tool(
    registry: ToolRegistry | None,
    name: str,
    args: dict[str, Any],
    calls: list[ToolCallRecord],
    *,
    approved: bool = False,
) -> ToolResult:
    """Execute a tool through ``ToolRegistry`` (never directly) and record timing and status."""
    started = time.perf_counter()
    result = await (registry or get_registry()).execute(name, args, approved=approved)
    calls.append(
        ToolCallRecord(
            tool=name,
            ok=result.ok,
            status=result.status,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=result.error,
        )
    )
    return result


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
