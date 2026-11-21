"""Ticket request and response shapes. Mirrors ``docs/API_CONTRACT.md`` (Tickets)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Channel, Severity, TicketStatus
from app.schemas.records import (
    CustomerOut,
    EscalationOut,
    ResolutionActionOut,
    SubscriptionOut,
    WorkspaceOut,
)

ApprovalState = Literal["not_required", "pending", "approved", "rejected"]
MAX_PAGE_SIZE = 100


class TicketCreate(BaseModel):
    customer_id: str
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)
    channel: Channel = Channel.WEB

    @field_validator("subject", "body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TicketPatch(BaseModel):
    """Only the fields the caller sends are changed; ``assigned_to: null`` un-assigns."""

    status: TicketStatus | None = None
    severity: Severity | None = None
    assigned_to: str | None = None


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    internal: bool = False

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class InfoRequest(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=10)

    @field_validator("questions")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        cleaned = [q.strip() for q in value if q.strip()]
        if not cleaned:
            raise ValueError("at least one non-blank question is required")
        return cleaned


class EscalateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    priority: Literal["normal", "urgent"] = "normal"

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TicketSummary(BaseModel):
    id: str
    ticket_number: str
    subject: str
    status: str
    severity: str | None = None
    category: str | None = None
    customer_id: str
    customer_name: str
    channel: str
    created_at: datetime
    updated_at: datetime
    escalation_required: bool
    approval_status: ApprovalState


class TicketOut(TicketSummary):
    body: str
    assigned_to: str | None = None
    resolved_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class TicketMessageOut(BaseModel):
    id: str
    ticket_id: str
    role: str
    author_name: str
    body: str
    internal: bool
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class TicketPage(BaseModel):
    items: list[TicketSummary]
    total: int
    page: int
    page_size: int


class TicketDetail(TicketOut):
    messages: list[TicketMessageOut]
    customer: CustomerOut
    subscription: SubscriptionOut | None = None
    workspaces: list[WorkspaceOut] = Field(default_factory=list)
    history: list[TicketSummary] = Field(default_factory=list)
    workflow: dict[str, Any] | None = None  # filled in Phase 10 (workflow runs)
    resolution_actions: list[ResolutionActionOut] = Field(default_factory=list)
    escalation: EscalationOut | None = None


class WorkflowEventOut(BaseModel):
    id: str
    workflow_id: str
    ticket_id: str
    event_type: str
    node: str | None = None
    tool: str | None = None
    message: str = ""
    duration_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
