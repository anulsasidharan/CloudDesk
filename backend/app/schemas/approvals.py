"""Approval request shapes (``docs/API_CONTRACT.md``, Approvals)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApprovalAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True
    description: str = ""


class ApprovalOut(BaseModel):
    id: str
    ticket_id: str
    ticket_number: str
    workflow_id: str
    action: ApprovalAction | None = None  # the first action; ``actions`` lists all of them
    actions: list[ApprovalAction] = Field(default_factory=list)
    risk_level: str
    reason: str
    requested_by: str = "ai"
    status: str
    decided_by: str | None = None
    decision_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class DecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class DecisionResult(BaseModel):
    approval: ApprovalOut
    workflow: dict[str, Any] | None = None
