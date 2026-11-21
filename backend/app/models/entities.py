"""SQLAlchemy 2 models for the 16 tables in ``CLAUDE.md`` section 6.

``database/schema.sql`` is the Postgres form of the same tables; ``tests/unit/test_schema_parity.py``
fails when the two drift. Status and category columns are plain strings guarded by CHECK
constraints built from ``app.schemas.common`` so the vocabulary has one home.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.schemas.common import (
    ActionStatus,
    ApprovalStatus,
    Category,
    Channel,
    EscalationStatus,
    EventType,
    IncidentStatus,
    MemoryKind,
    Plan,
    Role,
    RunStatus,
    SenderType,
    Severity,
    TicketStatus,
)


def _in(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


def _fk(target: str, *, nullable: bool = False, cascade: bool = False) -> Mapped[Any]:
    return mapped_column(
        String(36),
        ForeignKey(target, ondelete="CASCADE" if cascade else None),
        nullable=nullable,
        index=True,
    )


class Profile(Base, IdMixin, TimestampMixin):
    """A support-console user (agent, viewer, admin)."""

    __tablename__ = "profiles"
    __table_args__ = (_in("role", Role, "role"),)

    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.VIEWER.value)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Customer(Base, IdMixin, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (_in("plan", Plan, "plan"),)

    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(20), default=Plan.FREE.value)
    status: Mapped[str] = mapped_column(String(20), default="active")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class Subscription(Base, IdMixin, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (_in("plan", Plan, "plan"),)

    customer_id: Mapped[str] = _fk("customers.id", cascade=True)
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    seats_purchased: Mapped[int] = mapped_column(Integer, default=1)
    seats_used: Mapped[int] = mapped_column(Integer, default=0)
    seat_price: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    storage_limit_gb: Mapped[int] = mapped_column(Integer, default=15)
    storage_used_gb: Mapped[float] = mapped_column(Float, default=0)
    api_rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Workspace(Base, IdMixin, TimestampMixin):
    __tablename__ = "workspaces"

    customer_id: Mapped[str] = _fk("customers.id", cascade=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    region: Mapped[str] = mapped_column(String(20), default="us-east")
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    storage_used_gb: Mapped[float] = mapped_column(Float, default=0)
    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    external_sharing: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Product(Base, IdMixin, TimestampMixin):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="plan")
    monthly_price: Mapped[float] = mapped_column(Float, default=0)


class Ticket(Base, IdMixin, TimestampMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        _in("status", TicketStatus, "status"),
        _in("channel", Channel, "channel"),
        CheckConstraint(
            "category IS NULL OR category IN ("
            + ", ".join(f"'{member.value}'" for member in Category)
            + ")",
            name="category",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ("
            + ", ".join(f"'{member.value}'" for member in Severity)
            + ")",
            name="severity",
        ),
        Index("ix_tickets_status_created_at", "status", "created_at"),
    )

    number: Mapped[str] = mapped_column(String(20), unique=True)
    customer_id: Mapped[str] = _fk("customers.id")
    assigned_to: Mapped[str | None] = _fk("profiles.id", nullable=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default=Channel.WEB.value)
    status: Mapped[str] = mapped_column(String(30), default=TicketStatus.NEW.value)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    severity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "ticket_messages"
    __table_args__ = (_in("sender_type", SenderType, "sender_type"),)

    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    sender_type: Mapped[str] = mapped_column(String(20))
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)


class SupportArticle(Base, IdMixin, TimestampMixin):
    """A knowledge-base article. Chunks live in the vector store, not here."""

    __tablename__ = "support_articles"
    __table_args__ = (_in("category", Category, "category"),)

    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(40))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)


class Incident(Base, IdMixin, TimestampMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        _in("status", IncidentStatus, "status"),
        _in("severity", Severity, "severity"),
    )

    title: Mapped[str] = mapped_column(String(255))
    service: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default=IncidentStatus.ACTIVE.value)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.MEDIUM.value)
    description: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowRun(Base, IdMixin, TimestampMixin):
    """The workflow is data: ``state`` holds the serialised ``WorkflowState``."""

    __tablename__ = "workflow_runs"
    __table_args__ = (_in("status", RunStatus, "status"),)

    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30), default=RunStatus.PENDING.value)
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "workflow_events"
    __table_args__ = (_in("event_type", EventType, "event_type"),)

    workflow_id: Mapped[str] = _fk("workflow_runs.id", cascade=True)
    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    event_type: Mapped[str] = mapped_column(String(30))
    node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)


class ApprovalRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (_in("status", ApprovalStatus, "status"),)

    workflow_id: Mapped[str] = _fk("workflow_runs.id", cascade=True)
    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ApprovalStatus.PENDING.value)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decided_by: Mapped[str | None] = _fk("profiles.id", nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResolutionAction(Base, IdMixin, TimestampMixin):
    __tablename__ = "resolution_actions"
    __table_args__ = (_in("status", ActionStatus, "status"),)

    workflow_id: Mapped[str] = _fk("workflow_runs.id", cascade=True)
    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    approval_id: Mapped[str | None] = _fk("approval_requests.id", nullable=True)
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default=ActionStatus.PLANNED.value)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Escalation(Base, IdMixin, TimestampMixin):
    __tablename__ = "escalations"
    __table_args__ = (
        _in("status", EscalationStatus, "status"),
        _in("severity", Severity, "severity"),
    )

    ticket_id: Mapped[str] = _fk("tickets.id", cascade=True)
    workflow_id: Mapped[str | None] = _fk("workflow_runs.id", nullable=True)
    team: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.HIGH.value)
    status: Mapped[str] = mapped_column(String(20), default=EscalationStatus.OPEN.value)


class CustomerMemory(Base, IdMixin, TimestampMixin):
    """Long-term notes. ``content_hash`` de-duplicates exact repeats per customer and kind."""

    __tablename__ = "customer_memory"
    __table_args__ = (
        _in("kind", MemoryKind, "kind"),
        UniqueConstraint("customer_id", "kind", "content_hash", name="uq_customer_memory_note"),
    )

    customer_id: Mapped[str] = _fk("customers.id", cascade=True)
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_ticket_id: Mapped[str | None] = _fk("tickets.id", nullable=True)


class AuditLog(Base, IdMixin, TimestampMixin):
    """One row per state-changing request (N6)."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


TABLE_NAMES = tuple(Base.metadata.tables)
