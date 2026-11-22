"""Output schemas for the six specialist agents (CLAUDE.md 7.1). Every agent returns one of these."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import Category, Severity


class TokenUsage(BaseModel):
    """Tokens, calls and estimated cost. The fake provider always reports cost 0.0."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def merge(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
            calls=self.calls + other.calls,
        )


def merge_usage(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Reducer-friendly sum of two usage dicts (used by the graph state in Phase 10)."""
    return TokenUsage(**(left or {})).merge(TokenUsage(**(right or {}))).model_dump()


class ToolCallRecord(BaseModel):
    """What the tracer needs to log about one tool call. Never holds arguments or raw output."""

    tool: str
    ok: bool
    status: str
    duration_ms: int = 0
    error: str | None = None


# ---- Supervisor ---------------------------------------------------------------------------


class Classification(BaseModel):
    category: Category
    summary: str = Field(description="One line, no customer data beyond the issue itself")
    confidence: float = Field(ge=0, le=1, default=0.8)
    source: Literal["rules", "model"] = "model"


class SeverityAssessment(BaseModel):
    severity: Severity
    reason: str
    rule_ids: list[str] = Field(default_factory=list)
    injection_suspected: bool = False


class TicketSummary(BaseModel):
    summary: str


# ---- Customer -----------------------------------------------------------------------------


class CustomerContext(BaseModel):
    customer: dict[str, Any]
    subscription: dict[str, Any] | None = None
    workspaces: list[dict[str, Any]] = Field(default_factory=list)
    previous_tickets: list[dict[str, Any]] = Field(default_factory=list)
    memory_notes: list[str] = Field(default_factory=list)


# ---- Knowledge ----------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    id: str
    title: str
    source: str  # kb://slug#section
    snippet: str
    score: float
    url: str
    article_id: str


class PreviousCase(BaseModel):
    key: str
    category: str
    subject: str
    resolution: str
    steps: list[str] = Field(default_factory=list)
    similarity: float


class KnowledgeResult(BaseModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    previous_cases: list[PreviousCase] = Field(default_factory=list)


# ---- Troubleshooting ----------------------------------------------------------------------


class Diagnosis(BaseModel):
    probable_causes: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    service_status: dict[str, Any] | None = None
    confidence: float = Field(ge=0, le=1, default=0.7)

    def numbered(self) -> list[str]:
        return [f"{i}. {step}" for i, step in enumerate(self.steps, start=1)]


# ---- Resolution ---------------------------------------------------------------------------


class PlannedAction(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reason: str = ""


class ReplyDraft(BaseModel):
    """What the model writes. Actions are NOT here: they come from ``plan_actions`` (rules)."""

    summary: str
    customer_reply: str
    internal_notes: str = ""


class ResolutionPlan(BaseModel):
    summary: str
    customer_reply: str
    internal_notes: str = ""
    actions: list[PlannedAction] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)  # kb://slug#section, internal only
    validation_ok: bool = True
    validation_issues: list[str] = Field(default_factory=list)  # kinds only, never values


# ---- Escalation ---------------------------------------------------------------------------


class EscalationDecision(BaseModel):
    escalation_required: bool
    team: str | None = None
    reason: str = ""
    severity: Severity = Severity.HIGH
    policy_matched: bool = False
    rule_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.8)
