"""Risk level for a proposed resolution (CLAUDE.md 7.3). Pure rules, no model."""

from __future__ import annotations

from app.schemas.common import Severity
from app.schemas.workflow import ResolutionPlan

ROUTE_LOW = "low"
ROUTE_APPROVAL = "approval"
ROUTE_ESCALATION = "escalation"


def assess_risk(
    plan: ResolutionPlan,
    *,
    severity: Severity,
    policy_escalation: bool,
    injection_suspected: bool,
) -> tuple[str, list[str]]:
    """``high`` when money/account actions are planned, a policy rule fired, severity is critical,
    injection was seen, or output validation failed. ``medium`` for high severity. Else ``low``."""
    reasons: list[str] = []
    if any(a.requires_approval for a in plan.actions):
        reasons.append("plan contains an action that needs human approval")
    if policy_escalation:
        reasons.append("a policy escalation rule matched")
    if severity is Severity.CRITICAL:
        reasons.append("severity is critical")
    if injection_suspected:
        reasons.append("ticket text looked like a prompt injection")
    if not plan.validation_ok:
        reasons.append("the customer reply failed output validation")
    if reasons:
        return "high", reasons
    if severity is Severity.HIGH:
        return "medium", ["severity is high"]
    return "low", []


def choose_route(
    plan: ResolutionPlan, *, escalation_required: bool
) -> str:
    """Policy escalation beats approval; approval beats the low-risk path."""
    if escalation_required:
        return ROUTE_ESCALATION
    if any(a.requires_approval for a in plan.actions):
        return ROUTE_APPROVAL
    return ROUTE_LOW
