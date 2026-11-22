"""The graph state (CLAUDE.md 7.3). Every node returns a PARTIAL dict of these keys.

Reducers: ``errors`` and ``completed_nodes`` append, ``token_usage`` sums. Everything else is
overwritten by the node that owns it. Values are plain JSON (dicts, lists, strings) so the
checkpointer and ``workflow_runs.state`` can store them. Never put large documents in here.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas.workflow import merge_usage


class SupportState(TypedDict, total=False):
    # identity (set once by start_workflow)
    workflow_id: str
    ticket_id: str
    ticket_number: str
    customer_id: str
    plan_name: str | None
    subject: str
    body: str

    # specialist outputs
    classification: dict[str, Any]
    severity: str
    severity_reason: str
    rule_ids: list[str]
    injection_suspected: bool
    customer_context: dict[str, Any]
    evidence: list[dict[str, Any]]
    previous_cases: list[dict[str, Any]]
    diagnosis: dict[str, Any]
    resolution_plan: dict[str, Any]

    # risk and routing
    risk: dict[str, Any]
    route: str  # "low" | "approval" | "escalation"
    escalation_required: bool
    escalation_reason: str | None
    escalation_team: str | None
    approval_status: str

    # outcome
    actions: list[dict[str, Any]]
    final_response: str
    ticket_summary: str
    current_node: str

    # reducers
    errors: Annotated[list[str], operator.add]
    completed_nodes: Annotated[list[str], operator.add]
    token_usage: Annotated[dict[str, Any], merge_usage]
