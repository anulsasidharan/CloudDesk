"""Human approval and escalation nodes (F9, F10).

``human_approval`` pauses the graph with ``interrupt()``. LangGraph re-runs the node from the top
when it resumes, so everything above the ``interrupt()`` call must be free of side effects: it
only reads the state. The approval row, the ticket status and the ``approval_requested`` event
are written by ``workflow_service`` when it sees the pause, not here.

``escalation`` is the safe path. It is reached by a policy rule (route ``escalation``) or when a
person rejects the proposed action. It files the escalation and marks the ticket ``escalated``
through ``ToolRegistry``, like every other tool call.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core import database
from app.repositories import EscalationRepository, ResolutionActionRepository
from app.schemas.common import ActionStatus, Severity
from app.schemas.workflow import EscalationDecision, ToolCallRecord
from app.tools import get_registry
from langgraph.types import interrupt

from agents.nodes.common import dump, finish, plan_of, severity_of, tracer_for
from agents.specialists import EscalationAgent, run_tool
from agents.specialists.escalation import DEFAULT_TEAM
from agents.state import SupportState

logger = logging.getLogger("clouddesk.nodes")

APPROVAL = "human_approval"
ESCALATION = "escalation"

APPROVED = "approved"
REJECTED = "rejected"


async def human_approval(state: SupportState) -> dict[str, Any]:
    """Pause until a person decides. Resumed with ``{"approved": bool, "note": str}``."""
    pending = [dump(a) for a in plan_of(state).actions if a.requires_approval]
    # ---- nothing above this line may write anything: it runs again on resume ----
    decision = interrupt(
        {
            "kind": "approval",
            "workflow_id": state["workflow_id"],
            "ticket_id": state["ticket_id"],
            "actions": pending,
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
    note = decision.get("note") if isinstance(decision, dict) else None
    tracer = tracer_for(state)
    async with tracer.node(APPROVAL):
        status = APPROVED if approved else REJECTED
    return finish(APPROVAL, {"approval_status": status, "approval_note": note})


def _decision_for(state: SupportState) -> EscalationDecision:
    if state.get("approval_status") == REJECTED:
        note = (state.get("approval_note") or "").strip()
        reason = "A human approver rejected the proposed action"
        return EscalationDecision(
            escalation_required=True,
            team=DEFAULT_TEAM,
            reason=f"{reason}: {note}" if note else reason,
            severity=severity_of(state),
            confidence=1.0,
        )
    return EscalationDecision(
        escalation_required=True,
        team=state.get("escalation_team") or DEFAULT_TEAM,
        reason=state.get("escalation_reason") or "Escalated by policy",
        severity=Severity(state.get("escalation_severity") or state["severity"]),
        policy_matched=True,
        confidence=1.0,
    )


async def _skip_pending_actions(workflow_id: str) -> None:
    """A rejected plan must not leave actions looking like they are still waiting."""
    async with database.session_scope() as session:
        for row in await ResolutionActionRepository(session).list_for_workflow(workflow_id):
            if row.status == ActionStatus.AWAITING_APPROVAL.value:
                row.status = ActionStatus.SKIPPED.value
                row.result = {"reason": "approval rejected"}


async def escalation(state: SupportState) -> dict[str, Any]:
    """File the escalation, notify the team and mark the ticket ``escalated``. Safe to re-run."""
    tracer = tracer_for(state)
    errors: list[str] = []
    escalation_id: str | None = None
    async with tracer.node(ESCALATION):
        decision = _decision_for(state)
        calls: list[ToolCallRecord] = []
        async with database.session_scope() as session:
            existing = await EscalationRepository(session).for_workflow(state["workflow_id"])
            escalation_id = existing.id if existing else None
        if escalation_id is None:
            filed = await EscalationAgent().file(
                decision, state["ticket_id"], state["workflow_id"], get_registry()
            )
            calls.extend(filed.tool_calls)
            escalation_id = filed.output.get("escalation_id")
            if escalation_id is None:
                errors.append("escalation: could not be filed")
        if state.get("approval_status") == REJECTED:
            await _skip_pending_actions(state["workflow_id"])
        status_result = await run_tool(
            get_registry(),
            "update_ticket",
            {"ticket_id": state["ticket_id"], "status": "escalated"},
            calls,
        )
        if not status_result.ok:
            errors.append("escalation: ticket status not updated")
        await tracer.tool_calls(ESCALATION, calls)
    update: dict[str, Any] = {
        "escalation_required": True,
        "escalation_team": decision.team,
        "escalation_reason": decision.reason,
        "escalation_id": escalation_id,
        "final_response": plan_of(state).customer_reply,
    }
    if errors:
        update["errors"] = errors
    return finish(ESCALATION, update)
