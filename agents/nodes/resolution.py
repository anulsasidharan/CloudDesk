"""Resolution nodes: resolution_planning, risk_check, execute_resolution, memory_update (F8-F11)."""

from __future__ import annotations

import logging
from typing import Any

from app.core import database
from app.repositories import CustomerRepository, ResolutionActionRepository
from app.schemas.common import ActionStatus
from app.schemas.workflow import ToolCallRecord
from app.tools import get_registry

from agents.nodes.common import (
    classification_of,
    context_of,
    diagnosis_of,
    dump,
    evidence_of,
    finish,
    plan_of,
    severity_of,
    tracer_for,
)
from agents.risk import assess_risk, choose_route
from agents.specialists import EscalationAgent, ResolutionAgent, run_tool
from agents.state import SupportState
from memory.memory_service import MemoryService

logger = logging.getLogger("clouddesk.nodes")

PLANNING = "resolution_planning"
RISK = "risk_check"
EXECUTE = "execute_resolution"
MEMORY = "memory_update"


async def _other_customer_markers(customer_id: str) -> list[str]:
    """Names and companies of OTHER customers, used only to block leaks. Never stored in state."""
    async with database.session_scope() as session:
        others = [c for c in await CustomerRepository(session).list_all() if c.id != customer_id]
    return [m for c in others for m in (c.name, c.company) if m]


async def resolution_planning(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(PLANNING):
        result = await ResolutionAgent().run(
            ticket_id=state["ticket_id"],
            subject=state["subject"],
            body=state["body"],
            classification=classification_of(state),
            severity=severity_of(state),
            context=context_of(state),
            diagnosis=diagnosis_of(state),
            evidence=evidence_of(state),
            other_customer_markers=await _other_customer_markers(state["customer_id"]),
        )
        await tracer.llm(PLANNING, result.usage, result.duration_ms, "resolution plan")
    return finish(PLANNING, {"resolution_plan": dump(result.output)}, result.usage)


async def risk_check(state: SupportState) -> dict[str, Any]:
    """Policy escalation (rules win) and the risk level. Picks the route the graph follows."""
    tracer = tracer_for(state)
    async with tracer.node(RISK):
        severity = severity_of(state)
        result = await EscalationAgent().run(
            state["subject"], state["body"], state.get("plan_name"), severity
        )
        await tracer.llm(RISK, result.usage, result.duration_ms, "escalation judgement")
        decision = result.output
        plan = plan_of(state)
        level, reasons = assess_risk(
            plan,
            severity=severity,
            policy_escalation=decision.policy_matched,
            injection_suspected=bool(state.get("injection_suspected")),
        )
        route = choose_route(plan, escalation_required=decision.escalation_required)
    return finish(
        RISK,
        {
            "risk": {"level": level, "reasons": reasons},
            "route": route,
            "escalation_required": decision.escalation_required,
            "escalation_reason": decision.reason or None,
            "escalation_team": decision.team,
        },
        result.usage,
    )


async def execute_resolution(state: SupportState) -> dict[str, Any]:
    """Run the planned actions that need no approval, through ``ToolRegistry``.

    Actions that need approval are recorded as ``awaiting_approval`` and are NOT executed: the
    registry refuses them without ``approved=True``, and nothing in this phase sets it.
    Re-running is safe: an action already recorded for this run is skipped.
    """
    tracer = tracer_for(state)
    outcomes: list[dict[str, Any]] = []
    async with tracer.node(EXECUTE):
        plan = plan_of(state)
        registry = get_registry()
        calls: list[ToolCallRecord] = []
        for action in plan.actions:
            async with database.session_scope() as session:
                repo = ResolutionActionRepository(session)
                recorded = {a.tool for a in await repo.list_for_workflow(state["workflow_id"])}
                if action.tool in recorded:
                    continue
                row = await repo.add(
                    workflow_id=state["workflow_id"],
                    ticket_id=state["ticket_id"],
                    tool=action.tool,
                    args=action.args,
                    requires_approval=action.requires_approval,
                    status=(
                        ActionStatus.AWAITING_APPROVAL.value
                        if action.requires_approval
                        else ActionStatus.PLANNED.value
                    ),
                )
                row_id = row.id
            if action.requires_approval:
                outcomes.append(
                    {"id": row_id, "tool": action.tool, "status": ActionStatus.AWAITING_APPROVAL.value}
                )
                continue
            result = await run_tool(registry, action.tool, action.args, calls)
            status = ActionStatus.EXECUTED if result.ok else ActionStatus.FAILED
            async with database.session_scope() as session:
                row = await ResolutionActionRepository(session).get(row_id)
                row.status = status.value
                row.result = result.data if result.ok else {"error": result.error}
            outcomes.append({"id": row_id, "tool": action.tool, "status": status.value})
        await tracer.tool_calls(EXECUTE, calls)
    return finish(EXECUTE, {"actions": outcomes, "final_response": plan.customer_reply})


async def memory_update(state: SupportState) -> dict[str, Any]:
    """Remember the issue and resolution (F11). Best effort: a failure is recorded, not fatal."""
    tracer = tracer_for(state)
    errors: list[str] = []
    async with tracer.node(MEMORY):
        try:
            async with database.session_scope() as session:
                await MemoryService(session).record_resolution(
                    state["customer_id"],
                    state["ticket_id"],
                    issue_summary=classification_of(state).summary,
                    troubleshooting_steps=diagnosis_of(state).steps,
                    resolution_summary=plan_of(state).summary,
                )
        except Exception as exc:
            logger.warning("memory update failed", exc_info=True)
            errors.append(f"memory_update: {type(exc).__name__}")
    update: dict[str, Any] = {"errors": errors} if errors else {}
    return finish(MEMORY, update)
