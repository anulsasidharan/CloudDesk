"""Helpers every node shares: the tracer for this run and typed views of the state."""

from __future__ import annotations

from typing import Any

from app.core.observability import WorkflowTracer
from app.schemas.common import Category, Severity
from app.schemas.workflow import (
    Classification,
    CustomerContext,
    Diagnosis,
    EvidenceItem,
    PreviousCase,
    ResolutionPlan,
    TokenUsage,
)

from agents.state import SupportState


def tracer_for(state: SupportState) -> WorkflowTracer:
    return WorkflowTracer(state["workflow_id"], state["ticket_id"])


def dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def classification_of(state: SupportState) -> Classification:
    return Classification(**state["classification"])


def category_of(state: SupportState) -> Category:
    return Category(state["classification"]["category"])


def severity_of(state: SupportState) -> Severity:
    return Severity(state["severity"])


def context_of(state: SupportState) -> CustomerContext:
    return CustomerContext(**state["customer_context"])


def evidence_of(state: SupportState) -> list[EvidenceItem]:
    return [EvidenceItem(**e) for e in state.get("evidence", [])]


def cases_of(state: SupportState) -> list[PreviousCase]:
    return [PreviousCase(**c) for c in state.get("previous_cases", [])]


def diagnosis_of(state: SupportState) -> Diagnosis:
    return Diagnosis(**state["diagnosis"])


def plan_of(state: SupportState) -> ResolutionPlan:
    return ResolutionPlan(**state["resolution_plan"])


def finish(node: str, update: dict[str, Any], usage: TokenUsage | None = None) -> dict[str, Any]:
    """The partial state every node returns: its outputs plus the reducer fields."""
    result = {**update, "completed_nodes": [node], "current_node": node}
    if usage is not None:
        result["token_usage"] = dump(usage)
    return result
