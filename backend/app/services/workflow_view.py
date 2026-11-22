"""Turns a stored ``workflow_runs`` row into the ``WorkflowState`` JSON the console renders.

Read-only. Lives apart from ``workflow_service`` so ``ticket_service`` can embed the latest run in
``TicketDetail`` without importing the service that runs workflows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WorkflowRun
from app.repositories import ApprovalRepository, ResolutionActionRepository, WorkflowRunRepository
from app.schemas.common import RunStatus

STATUS_FOR_RUN = {
    RunStatus.PENDING.value: "running",
    RunStatus.RUNNING.value: "running",
    RunStatus.WAITING_ON_APPROVAL.value: "waiting_for_approval",
    RunStatus.COMPLETED.value: "completed",
    RunStatus.FAILED.value: "failed",
}
ACTION_STATUS = {"awaiting_approval": "pending_approval", "skipped": "rejected"}


def _action_out(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "tool": row.tool,
        "arguments": row.args,
        "status": ACTION_STATUS.get(row.status, row.status),
        "result": row.result,
        "requires_approval": row.requires_approval,
        "created_at": row.created_at.isoformat(),
    }


def _plan_out(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return None
    return {
        "summary": plan["summary"],
        "customer_response": plan["customer_reply"],
        "internal_notes": plan.get("internal_notes", ""),
        "actions": [
            {
                "tool": a["tool"],
                "arguments": a.get("args", {}),
                "requires_approval": a.get("requires_approval", False),
                "description": a.get("reason", ""),
            }
            for a in plan.get("actions", [])
        ],
    }


def _context_out(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not context:
        return None
    workspaces = context.get("workspaces") or []
    return {
        "customer": context["customer"],
        "subscription": context.get("subscription"),
        "workspace": workspaces[0] if workspaces else None,
        "previous_tickets": context.get("previous_tickets", []),
        "memory_notes": context.get("memory_notes", []),
    }


def _usage_out(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage or {}
    return {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "estimated_cost_usd": usage.get("cost_usd", 0.0),
    }


def _status(run: WorkflowRun, state: dict[str, Any]) -> str:
    """The run status as the console names it. A finished run that filed an escalation is ``escalated``."""
    if run.status == RunStatus.COMPLETED.value and state.get("escalation_id"):
        return "escalated"
    return STATUS_FOR_RUN.get(run.status, run.status)


def build_view(run: WorkflowRun, actions: list[Any], approval: Any = None) -> dict[str, Any]:
    state = run.state or {}
    classification = state.get("classification")
    diagnosis = state.get("diagnosis")
    finished = run.completed_at
    errors = list(state.get("errors", []))
    if run.error:
        errors.append(run.error)
    return {
        "workflow_id": run.id,
        "ticket_id": run.ticket_id,
        "status": _status(run, state),
        "current_node": run.current_node,
        "completed_nodes": state.get("completed_nodes", []),
        "classification": (
            {
                "category": classification["category"],
                "intent": classification["category"],
                "summary": classification["summary"],
                "confidence": classification.get("confidence", 0.0),
            }
            if classification
            else None
        ),
        "severity": state.get("severity"),
        "severity_reason": state.get("severity_reason"),
        "customer_context": _context_out(state.get("customer_context")),
        "retrieved_docs": state.get("evidence", []),
        "previous_cases": [
            {
                "ticket_number": c["key"],
                "subject": c["subject"],
                "resolution_summary": c["resolution"],
                "similarity": c["similarity"],
            }
            for c in state.get("previous_cases", [])
        ],
        "diagnosis": (
            {
                "problem": classification["summary"] if classification else "",
                "probable_causes": diagnosis["probable_causes"],
                "troubleshooting_steps": diagnosis["steps"],
                "confidence": diagnosis.get("confidence", 0.0),
            }
            if diagnosis
            else None
        ),
        "resolution_plan": _plan_out(state.get("resolution_plan")),
        "actions": [_action_out(a) for a in actions],
        "risk": state.get("risk"),
        "escalation_required": bool(state.get("escalation_required", False)),
        "escalation_reason": state.get("escalation_reason"),
        "approval_status": approval.status if approval else state.get("approval_status", "not_required"),
        "approval_request_id": approval.id if approval else None,
        "final_response": state.get("final_response"),
        "ticket_summary": state.get("ticket_summary"),
        "errors": errors,
        "started_at": run.created_at.isoformat(),
        "finished_at": finished.isoformat() if finished else None,
        "duration_ms": (
            int((finished - run.created_at).total_seconds() * 1000)
            if finished and run.created_at.tzinfo == finished.tzinfo
            else None
        ),
        "token_usage": _usage_out(state.get("token_usage")),
    }


async def latest_view(session: AsyncSession, ticket_id: str) -> dict[str, Any] | None:
    """The latest run for a ticket as ``WorkflowState`` JSON, or ``None`` if it never ran."""
    run = await WorkflowRunRepository(session).latest_for_ticket(ticket_id)
    if run is None:
        return None
    actions = await ResolutionActionRepository(session).list_for_workflow(run.id)
    approval = await ApprovalRepository(session).latest_for_workflow(run.id)
    return build_view(run, actions, approval)
