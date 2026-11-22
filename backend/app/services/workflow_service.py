"""Starting and running the support workflow (CLAUDE.md 4.1 steps 2-4). Knows nothing about HTTP.

``create_run`` records the run and commits, so the background task can see it. ``start_workflow``
streams the graph and saves the state after EVERY node, so the console can poll progress. When the
graph pauses at ``human_approval`` the run becomes ``waiting_on_approval`` and an approval request
is recorded; ``resume_workflow`` continues it with the human decision (CLAUDE.md 4.1 steps 5-8).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.observability import WorkflowTracer
from app.models.entities import WorkflowRun
from app.repositories import (
    ApprovalRepository,
    CustomerRepository,
    ResolutionActionRepository,
    TicketRepository,
    WorkflowRunRepository,
)
from app.schemas.common import ActionStatus, ApprovalStatus, EventType, RunStatus, TicketStatus
from app.services import ticket_service, workflow_view

logger = logging.getLogger("clouddesk.workflow")

ACTIVE_RUN = (RunStatus.PENDING.value, RunStatus.RUNNING.value)


class WorkflowConflictError(RuntimeError):
    """The ticket is waiting on a person or already has a run in progress (HTTP 409)."""


class NoWorkflowError(LookupError):
    """The ticket has never been run."""


async def create_run(session: AsyncSession, ticket_ref: str) -> WorkflowRun:
    """Record a new run for the ticket and commit it. Raises ``WorkflowConflictError`` on a clash."""
    ticket = await ticket_service.find_ticket(session, ticket_ref)
    if ticket.status == TicketStatus.WAITING_ON_APPROVAL.value:
        raise WorkflowConflictError("Ticket is waiting on approval")
    runs = WorkflowRunRepository(session)
    latest = await runs.latest_for_ticket(ticket.id)
    if latest is not None and latest.status in ACTIVE_RUN:
        raise WorkflowConflictError("A workflow is already running for this ticket")
    run = await runs.add(
        ticket_id=ticket.id,
        thread_id=str(uuid.uuid4()),
        status=RunStatus.RUNNING.value,
        state={},
    )
    await session.commit()  # the background task opens its own session and must see this row
    return run


async def _initial_state(run_id: str) -> dict[str, Any]:
    async with database.session_scope() as session:
        run = await WorkflowRunRepository(session).get(run_id)
        ticket = await TicketRepository(session).get(run.ticket_id)
        customer = await CustomerRepository(session).get(ticket.customer_id)
        return {
            "workflow_id": run.id,
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "customer_id": ticket.customer_id,
            "plan_name": customer.plan if customer else None,
            "subject": ticket.subject,
            "body": ticket.body,
            "approval_status": "not_required",
            "thread_id": run.thread_id,
        }


async def _save(run_id: str, state: dict[str, Any]) -> None:
    async with database.session_scope() as session:
        repo = WorkflowRunRepository(session)
        run = await repo.get(run_id)
        await repo.save_state(run, _jsonable(state), current_node=state.get("current_node"))


def _jsonable(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state.pop("thread_id", None)
    return state


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _drive(run_id: str, graph_input: Any, thread_id: str, tracer: WorkflowTracer) -> None:
    """Stream the graph, saving the state after EVERY node, then complete the run or record the pause."""
    from agents.graph import get_graph

    graph = await get_graph()
    config = _config(thread_id)
    state: dict[str, Any] = {}
    async for chunk in graph.astream(graph_input, config, stream_mode="values"):
        if "__interrupt__" in chunk:  # LangGraph reports a pause as an extra chunk
            chunk = {k: v for k, v in chunk.items() if k != "__interrupt__"}
            if not chunk:
                continue
        state = chunk
        await _save(run_id, state)
    snapshot = await graph.aget_state(config)
    if snapshot.next:  # the graph stopped before END: it is waiting for a person
        await _handle_interrupt(run_id, state, tracer)
        return
    async with database.session_scope() as session:
        repo = WorkflowRunRepository(session)
        await repo.set_status(await repo.get(run_id), RunStatus.COMPLETED)
    usage = state.get("token_usage", {})
    await tracer.emit(
        EventType.WORKFLOW_COMPLETED,
        message="workflow completed",
        payload={"completed_nodes": len(state.get("completed_nodes", []))},
    )
    logger.info("workflow completed", extra={"workflow_id": run_id, "tokens": usage.get("total_tokens", 0)})


async def _handle_interrupt(run_id: str, state: dict[str, Any], tracer: WorkflowTracer) -> None:
    """The graph paused at ``human_approval``: record the request, hold the ticket, tell the console.

    Idempotent: a second call for the same run reuses the pending request.
    """
    plan = state.get("resolution_plan") or {}
    pending = [
        {
            "tool": a["tool"],
            "arguments": a.get("args", {}),
            "requires_approval": True,
            "description": a.get("reason", ""),
        }
        for a in plan.get("actions", [])
        if a.get("requires_approval")
    ]
    risk = state.get("risk") or {}
    async with database.session_scope() as session:
        runs = WorkflowRunRepository(session)
        run = await runs.get(run_id)
        approvals = ApprovalRepository(session)
        approval = await approvals.latest_for_workflow(run_id)
        if approval is None or approval.status != ApprovalStatus.PENDING.value:
            names = ", ".join(a["tool"] for a in pending) or "an action"
            approval = await approvals.add(
                workflow_id=run_id,
                ticket_id=run.ticket_id,
                summary=f"Approve {names}: {plan.get('summary', '')}".strip(),
                status=ApprovalStatus.PENDING.value,
                payload={
                    "action": pending[0] if pending else None,
                    "actions": pending,
                    "risk_level": risk.get("level", "high"),
                    "reason": "; ".join(risk.get("reasons", [])) or "Needs human approval",
                },
            )
        actions = ResolutionActionRepository(session)
        for item in pending:
            if await actions.for_workflow_tool(run_id, item["tool"]) is None:
                await actions.add(
                    workflow_id=run_id,
                    ticket_id=run.ticket_id,
                    approval_id=approval.id,
                    tool=item["tool"],
                    args=item["arguments"],
                    requires_approval=True,
                    status=ActionStatus.AWAITING_APPROVAL.value,
                )
        ticket = await TicketRepository(session).get(run.ticket_id)
        await TicketRepository(session).set_status(ticket, TicketStatus.WAITING_ON_APPROVAL)
        await runs.save_state(
            run,
            _jsonable({**state, "approval_status": "pending", "approval_request_id": approval.id}),
            current_node="human_approval",
        )
        await runs.set_status(run, RunStatus.WAITING_ON_APPROVAL)
        approval_id = approval.id
    await tracer.emit(
        EventType.APPROVAL_REQUESTED,
        node="human_approval",
        message="waiting for human approval",
        payload={"approval_id": approval_id, "tools": [a["tool"] for a in pending]},
    )
    logger.info("workflow paused for approval", extra={"workflow_id": run_id})


async def _fail(run_id: str, exc: Exception) -> None:
    logger.exception("workflow failed: %s", type(exc).__name__, extra={"workflow_id": run_id})
    try:
        async with database.session_scope() as session:
            repo = WorkflowRunRepository(session)
            run = await repo.get(run_id)
            if run is not None:
                await repo.set_status(run, RunStatus.FAILED, error=f"{type(exc).__name__}")
    except Exception:
        logger.exception("could not record workflow failure")


async def start_workflow(run_id: str) -> None:
    """Run the graph for ``run_id`` until it ends or pauses. Never raises: a failure becomes ``failed``."""
    try:
        initial = await _initial_state(run_id)
        thread_id = initial.pop("thread_id")
        tracer = WorkflowTracer(initial["workflow_id"], initial["ticket_id"])
        await _drive(run_id, initial, thread_id, tracer)
    except Exception as exc:  # noqa: BLE001 - a background run must never raise
        await _fail(run_id, exc)


async def resume_workflow(run_id: str, *, approved: bool, note: str | None = None) -> None:
    """Continue a paused run with the human decision (``Command(resume=...)``). Never raises."""
    from langgraph.types import Command

    try:
        async with database.session_scope() as session:
            run = await WorkflowRunRepository(session).get(run_id)
            thread_id, ticket_id = run.thread_id, run.ticket_id
        tracer = WorkflowTracer(run_id, ticket_id)
        await _drive(run_id, Command(resume={"approved": approved, "note": note}), thread_id, tracer)
    except Exception as exc:  # noqa: BLE001 - a background run must never raise
        await _fail(run_id, exc)


async def get_workflow(session: AsyncSession, ticket_ref: str) -> dict[str, Any]:
    ticket = await ticket_service.find_ticket(session, ticket_ref)
    view = await workflow_view.latest_view(session, ticket.id)
    if view is None:
        raise NoWorkflowError(ticket.number)
    return view
