"""Starting and running the support workflow (CLAUDE.md 4.1 steps 2-4). Knows nothing about HTTP.

``create_run`` records the run and commits, so the background task can see it. ``start_workflow``
streams the graph and saves the state after EVERY node, so the console can poll progress.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.observability import WorkflowTracer
from app.models.entities import WorkflowRun
from app.repositories import CustomerRepository, TicketRepository, WorkflowRunRepository
from app.schemas.common import EventType, RunStatus, TicketStatus
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


async def start_workflow(run_id: str) -> None:
    """Run the graph for ``run_id`` to the end. Never raises: a failure becomes status ``failed``."""
    from agents.graph import get_graph

    state: dict[str, Any] = {}
    tracer: WorkflowTracer | None = None
    try:
        initial = await _initial_state(run_id)
        thread_id = initial.pop("thread_id")
        tracer = WorkflowTracer(initial["workflow_id"], initial["ticket_id"])
        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        async for state in graph.astream(initial, config, stream_mode="values"):
            await _save(run_id, state)  # after every node
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
    except Exception as exc:
        logger.exception("workflow failed", extra={"workflow_id": run_id})
        try:
            async with database.session_scope() as session:
                repo = WorkflowRunRepository(session)
                run = await repo.get(run_id)
                if run is not None:
                    await repo.set_status(run, RunStatus.FAILED, error=f"{type(exc).__name__}")
        except Exception:
            logger.exception("could not record workflow failure")


async def get_workflow(session: AsyncSession, ticket_ref: str) -> dict[str, Any]:
    ticket = await ticket_service.find_ticket(session, ticket_ref)
    view = await workflow_view.latest_view(session, ticket.id)
    if view is None:
        raise NoWorkflowError(ticket.number)
    return view
