"""WorkflowTracer (F13): writes ``workflow_events`` so every node, tool and model call is inspectable.

Telemetry must never break a run, so every public method swallows its own errors. Only names,
statuses, timings and token counts are recorded. Raw prompts, ticket bodies and tool arguments
are never written (CLAUDE.md section 16).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.core import database
from app.repositories import WorkflowEventRepository
from app.schemas.common import EventType
from app.schemas.workflow import TokenUsage, ToolCallRecord

logger = logging.getLogger("clouddesk.trace")


class WorkflowTracer:
    def __init__(self, workflow_id: str, ticket_id: str) -> None:
        self.workflow_id = workflow_id
        self.ticket_id = ticket_id

    async def emit(
        self,
        event_type: EventType,
        *,
        node: str | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        """Record one event in its own transaction. Never raises."""
        try:
            body = {"message": message, **(payload or {})}
            async with database.session_scope() as session:
                await WorkflowEventRepository(session).add(
                    workflow_id=self.workflow_id,
                    ticket_id=self.ticket_id,
                    event_type=event_type.value,
                    node=node,
                    payload=body,
                    duration_ms=duration_ms,
                    input_tokens=usage.input_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                    cost_usd=usage.cost_usd if usage else 0.0,
                )
        except Exception:
            logger.warning("trace event dropped: %s", event_type.value, exc_info=True)

    @asynccontextmanager
    async def node(self, name: str) -> AsyncIterator[None]:
        """``node_started`` / ``node_completed`` with duration. A failing node logs ``error``."""
        started = time.perf_counter()
        await self.emit(EventType.NODE_STARTED, node=name, message=f"{name} started")
        try:
            yield
        except Exception as exc:
            await self.emit(
                EventType.ERROR,
                node=name,
                message=f"{name} failed",
                payload={"error_type": type(exc).__name__},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        await self.emit(
            EventType.NODE_COMPLETED,
            node=name,
            message=f"{name} completed",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def tool_calls(self, node: str, calls: list[ToolCallRecord]) -> None:
        for call in calls:
            await self.emit(
                EventType.TOOL_CALLED,
                node=node,
                message=f"{call.tool}: {call.status}",
                payload={"tool": call.tool, "ok": call.ok, "status": call.status, "error": call.error},
                duration_ms=call.duration_ms,
            )

    async def llm(self, node: str, usage: TokenUsage, duration_ms: int, label: str) -> None:
        if usage.calls == 0:  # a node that made no model call has nothing to record
            return
        await self.emit(
            EventType.LLM_CALLED,
            node=node,
            message=f"{label}: {usage.total_tokens} tokens",
            payload={"label": label, "calls": usage.calls, "total_tokens": usage.total_tokens},
            duration_ms=duration_ms,
            usage=usage,
        )
