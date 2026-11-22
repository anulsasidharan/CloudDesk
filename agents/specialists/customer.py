"""Customer Agent (F4): who is this, what do they pay for, what happened before. No model call."""

from __future__ import annotations

import time

from app.core import database
from app.repositories import WorkspaceRepository
from app.schemas.workflow import CustomerContext, ToolCallRecord
from app.tools import ToolRegistry

from agents.specialists.base import AgentResult, elapsed_ms, run_tool
from memory.memory_service import MemoryService


class CustomerAgent:
    async def run(
        self,
        customer_id: str,
        ticket_id: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> AgentResult[CustomerContext]:
        started = time.perf_counter()
        calls: list[ToolCallRecord] = []

        customer = await run_tool(registry, "get_customer", {"customer_id": customer_id}, calls)
        if not customer.ok or customer.data is None:
            raise LookupError(f"customer not found: {customer_id}")
        subscription = await run_tool(
            registry, "get_subscription", {"customer_id": customer_id}, calls
        )
        history = await run_tool(
            registry,
            "get_ticket_history",
            {"customer_id": customer_id, "exclude_ticket_id": ticket_id, "limit": 5},
            calls,
        )

        # Workspaces and long-term notes have no tool; they come from a repository and the memory
        # facade. Both are scoped to this one customer.
        async with database.session_scope() as session:
            workspaces = [
                {
                    "id": w.id,
                    "name": w.name,
                    "members": w.member_count,
                    "sso_enabled": w.sso_enabled,
                    "mfa_required": w.mfa_required,
                    "external_sharing": w.external_sharing,
                }
                for w in await WorkspaceRepository(session).list_for_customer(customer_id)
            ]
            notes = await MemoryService(session).recall_customer(customer_id)

        context = CustomerContext(
            customer=customer.data,
            subscription=subscription.data if subscription.ok else None,
            workspaces=workspaces,
            previous_tickets=(history.data or {}).get("tickets", []) if history.ok else [],
            memory_notes=[f"{n.kind}: {n.content}" for n in notes],
        )
        return AgentResult(context, duration_ms=elapsed_ms(started), tool_calls=calls)
