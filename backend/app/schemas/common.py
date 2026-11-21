"""Shared domain vocabulary. Any new category is added here first (CLAUDE.md section 5)."""

from enum import StrEnum


class Category(StrEnum):
    LOGIN_ISSUE = "login_issue"
    BILLING = "billing"
    API_FAILURE = "api_failure"
    WORKSPACE_PERMISSIONS = "workspace_permissions"
    STORAGE_QUOTA = "storage_quota"
    INTEGRATION = "integration"
    FEATURE_REQUEST = "feature_request"
    ACCOUNT = "account"
    SECURITY = "security"
    OTHER = "other"


class TicketStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    WAITING_ON_APPROVAL = "waiting_on_approval"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Channel(StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    WEB = "web"
    API = "api"


class Role(StrEnum):
    VIEWER = "viewer"
    AGENT = "agent"
    ADMIN = "admin"


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    PAST_ISSUE = "past_issue"
    TROUBLESHOOTING = "troubleshooting"
    NOTE = "note"


class IncidentStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_ON_APPROVAL = "waiting_on_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EscalationStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class EventType(StrEnum):
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    TOOL_CALLED = "tool_called"
    LLM_CALLED = "llm_called"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    ERROR = "error"
    WORKFLOW_COMPLETED = "workflow_completed"
