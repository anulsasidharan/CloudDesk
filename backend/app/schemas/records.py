"""Read-only shapes for customer-side records. Leaf module: imports nothing from the API schemas.

Field names mirror the SQLAlchemy models (see ``docs/API_CONTRACT.md``, Customers).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerOut(_Out):
    id: str
    name: str
    email: str
    company: str
    plan: str
    status: str
    timezone: str
    created_at: datetime


class SubscriptionOut(_Out):
    id: str
    customer_id: str
    plan: str
    status: str
    billing_cycle: str
    seats_purchased: int
    seats_used: int
    seat_price: float
    currency: str
    storage_limit_gb: int
    storage_used_gb: float
    api_rate_limit_per_minute: int
    renews_at: datetime | None = None


class WorkspaceOut(_Out):
    id: str
    customer_id: str
    name: str
    slug: str
    region: str
    member_count: int
    storage_used_gb: float
    sso_enabled: bool
    mfa_required: bool
    external_sharing: bool


class CustomerMemoryOut(_Out):
    id: str
    customer_id: str
    kind: str
    content: str
    source_ticket_id: str | None = None
    created_at: datetime


class ResolutionActionOut(BaseModel):
    id: str
    ticket_id: str
    workflow_id: str
    tool: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any] | None = None
    requires_approval: bool
    created_at: datetime


class EscalationOut(_Out):
    id: str
    ticket_id: str
    team: str
    reason: str
    severity: str
    status: str
    created_at: datetime
