"""Workflow runs, events, actions, approvals and escalations."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.models.entities import (
    ApprovalRequest,
    Escalation,
    ResolutionAction,
    WorkflowEvent,
    WorkflowRun,
)
from app.repositories.base import BaseRepository
from app.schemas.common import ApprovalStatus, RunStatus


class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    model = WorkflowRun

    async def latest_for_ticket(self, ticket_id: str) -> WorkflowRun | None:
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.ticket_id == ticket_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def save_state(
        self, run: WorkflowRun, state: dict[str, Any], *, current_node: str | None = None
    ) -> WorkflowRun:
        run.state = state
        if current_node is not None:
            run.current_node = current_node
        await self.session.flush()
        return run

    async def set_status(
        self, run: WorkflowRun, status: RunStatus, *, error: str | None = None
    ) -> WorkflowRun:
        run.status = status.value
        run.error = error
        if status in (RunStatus.COMPLETED, RunStatus.FAILED):
            run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run


class WorkflowEventRepository(BaseRepository[WorkflowEvent]):
    model = WorkflowEvent

    async def list_for_ticket(self, ticket_id: str) -> list[WorkflowEvent]:
        stmt = (
            select(WorkflowEvent)
            .where(WorkflowEvent.ticket_id == ticket_id)
            .order_by(WorkflowEvent.created_at, WorkflowEvent.id)
        )
        return list((await self.session.execute(stmt)).scalars())


class ResolutionActionRepository(BaseRepository[ResolutionAction]):
    model = ResolutionAction

    async def list_for_workflow(self, workflow_id: str) -> list[ResolutionAction]:
        stmt = (
            select(ResolutionAction)
            .where(ResolutionAction.workflow_id == workflow_id)
            .order_by(ResolutionAction.created_at, ResolutionAction.id)
        )
        return list((await self.session.execute(stmt)).scalars())


class ApprovalRepository(BaseRepository[ApprovalRequest]):
    model = ApprovalRequest

    async def pending(self) -> list[ApprovalRequest]:
        stmt = (
            select(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRequest.created_at)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def pending_for_ticket(self, ticket_id: str) -> ApprovalRequest | None:
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.ticket_id == ticket_id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def decide(
        self,
        approval: ApprovalRequest,
        status: ApprovalStatus,
        *,
        decided_by: str | None,
        note: str | None = None,
    ) -> ApprovalRequest:
        approval.status = status.value
        approval.decided_by = decided_by
        approval.decision_note = note
        approval.decided_at = datetime.now(UTC)
        await self.session.flush()
        return approval


class EscalationRepository(BaseRepository[Escalation]):
    model = Escalation

    async def list_for_ticket(self, ticket_id: str) -> list[Escalation]:
        stmt = (
            select(Escalation)
            .where(Escalation.ticket_id == ticket_id)
            .order_by(Escalation.created_at)
        )
        return list((await self.session.execute(stmt)).scalars())
