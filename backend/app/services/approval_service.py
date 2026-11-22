"""Approving and rejecting paused workflows (F9). Knows nothing about HTTP.

``decide`` claims the request with one conditional UPDATE (so a double click cannot run the action
twice), commits, then resumes the graph with the decision. The graph runs the approved actions
through ``ToolRegistry``; this service never calls a tool itself.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import WorkflowTracer
from app.core.security import AuthUser
from app.models.entities import ApprovalRequest
from app.repositories import ApprovalRepository, TicketRepository, WorkflowRunRepository
from app.schemas.approvals import ApprovalOut, DecisionResult
from app.schemas.common import ApprovalStatus, EventType, RunStatus, TicketStatus
from app.services import workflow_service, workflow_view


class ApprovalNotFoundError(LookupError):
    """No approval request has this id."""


class ApprovalConflictError(RuntimeError):
    """The request was already decided, or its run is not paused (HTTP 409)."""


async def _out(session: AsyncSession, approval: ApprovalRequest) -> ApprovalOut:
    ticket = await TicketRepository(session).get(approval.ticket_id)
    payload = approval.payload or {}
    return ApprovalOut(
        id=approval.id,
        ticket_id=approval.ticket_id,
        ticket_number=ticket.number if ticket else "",
        workflow_id=approval.workflow_id,
        action=payload.get("action"),
        actions=payload.get("actions", []),
        risk_level=payload.get("risk_level", "high"),
        reason=payload.get("reason", approval.summary),
        status=approval.status,
        decided_by=approval.decided_by,
        decision_note=approval.decision_note,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


async def list_approvals(session: AsyncSession, status: ApprovalStatus | None) -> list[ApprovalOut]:
    rows = await ApprovalRepository(session).list_filtered(status.value if status else None)
    return [await _out(session, row) for row in rows]


async def get_approval(session: AsyncSession, approval_id: str) -> ApprovalOut:
    approval = await ApprovalRepository(session).get(approval_id)
    if approval is None:
        raise ApprovalNotFoundError(approval_id)
    return await _out(session, approval)


async def decide(
    session: AsyncSession,
    approval_id: str,
    *,
    approved: bool,
    note: str | None,
    caller: AuthUser,
) -> DecisionResult:
    """Record the decision, then resume the paused run. Raises on a missing or settled request."""
    approvals = ApprovalRepository(session)
    approval = await approvals.get(approval_id)
    if approval is None:
        raise ApprovalNotFoundError(approval_id)
    runs = WorkflowRunRepository(session)
    run = await runs.get(approval.workflow_id)
    if approval.status != ApprovalStatus.PENDING.value:
        raise ApprovalConflictError("Approval has already been decided")
    if run is None or run.status != RunStatus.WAITING_ON_APPROVAL.value:
        raise ApprovalConflictError("Workflow is not waiting for approval")

    status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    if not await approvals.claim(approval_id, status, decided_by=caller.id, note=note):
        raise ApprovalConflictError("Approval has already been decided")
    await session.refresh(approval)
    await runs.set_status(run, RunStatus.RUNNING)
    ticket = await TicketRepository(session).get(approval.ticket_id)
    await TicketRepository(session).set_status(ticket, TicketStatus.IN_PROGRESS)
    run_id, ticket_id = run.id, approval.ticket_id
    await session.commit()  # the resumed graph opens its own sessions and must see the decision

    await WorkflowTracer(run_id, ticket_id).emit(
        EventType.APPROVAL_RESOLVED,
        node="human_approval",
        message=f"approval {status.value}",
        payload={"approval_id": approval_id, "decision": status.value, "decided_by": caller.id},
    )
    await workflow_service.resume_workflow(run_id, approved=approved, note=note)

    session.expire_all()  # the graph wrote through other sessions; drop what this one cached
    approval = await approvals.get(approval_id)
    return DecisionResult(
        approval=await _out(session, approval),
        workflow=await workflow_view.latest_view(session, ticket_id),
    )
