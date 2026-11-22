"""Graph shape, routing, risk levels, reducers (P10-1, P10-4, P10-5)."""

import typing

from app.schemas.common import Category, Severity
from app.schemas.workflow import Classification, PlannedAction, ResolutionPlan, merge_usage

from agents.graph import (
    APPROVAL_TARGETS,
    GRAPH_EDGES,
    GRAPH_NODES,
    ROUTE_TARGETS,
    build_graph,
    route_after_approval,
    route_after_risk,
)
from agents.risk import assess_risk, choose_route
from agents.state import SupportState

EXPECTED_ORDER = [
    "understand_ticket",
    "classify_severity",
    "customer_context",
    "knowledge_retrieval",
    "troubleshooting",
    "resolution_planning",
    "risk_check",
    "human_approval",
    "execute_resolution",
    "escalation",
    "ticket_summary",
    "memory_update",
]


def _plan(*, approval: bool = False, valid: bool = True) -> ResolutionPlan:
    action = PlannedAction(tool="create_refund_request", requires_approval=approval)
    return ResolutionPlan(summary="s", customer_reply="r", actions=[action], validation_ok=valid)


def _plain() -> ResolutionPlan:
    return ResolutionPlan(summary="s", customer_reply="r")


def _risk(plan, severity=Severity.LOW, policy=False, injection=False):
    return assess_risk(
        plan, severity=severity, policy_escalation=policy, injection_suspected=injection
    )


def test_graph_nodes_are_in_pipeline_order():
    assert GRAPH_NODES == EXPECTED_ORDER


def test_graph_edges_form_one_chain_to_end():
    pairs = set(GRAPH_EDGES)
    assert ("understand_ticket", "classify_severity") in pairs
    assert ("risk_check", "execute_resolution") in pairs
    assert ("risk_check", "human_approval") in pairs
    assert ("risk_check", "escalation") in pairs
    assert ("human_approval", "execute_resolution") in pairs
    assert ("human_approval", "escalation") in pairs
    assert ("execute_resolution", "ticket_summary") in pairs
    assert ("escalation", "ticket_summary") in pairs
    assert ("memory_update", "__end__") in pairs


def test_graph_compiles_and_has_every_node():
    compiled = build_graph()
    assert set(EXPECTED_ORDER) <= set(compiled.get_graph().nodes)


def test_every_route_has_a_target():
    assert set(ROUTE_TARGETS) == {"low", "approval", "escalation"}
    assert route_after_risk(SupportState(route="approval")) == "approval"
    assert route_after_risk(SupportState()) == "low"


def test_routes_point_at_the_phase_11_nodes():
    assert ROUTE_TARGETS == {
        "low": "execute_resolution",
        "approval": "human_approval",
        "escalation": "escalation",
    }
    assert APPROVAL_TARGETS == {"approved": "execute_resolution", "rejected": "escalation"}


def test_only_an_explicit_approval_runs_the_actions():
    assert route_after_approval(SupportState(approval_status="approved")) == "approved"
    for status in ("rejected", "pending", "not_required", ""):
        assert route_after_approval(SupportState(approval_status=status)) == "rejected"
    assert route_after_approval(SupportState()) == "rejected"


def test_risk_low_for_plain_plan():
    assert _risk(_plain()) == ("low", [])


def test_risk_high_triggers():
    cases = [
        _risk(_plan(approval=True)),
        _risk(_plain(), severity=Severity.CRITICAL),
        _risk(_plain(), policy=True),
        _risk(_plain(), injection=True),
        _risk(_plan(valid=False)),
    ]
    for level, reasons in cases:
        assert level == "high" and reasons


def test_risk_medium_for_high_severity():
    assert _risk(_plain(), severity=Severity.HIGH)[0] == "medium"


def test_policy_escalation_beats_approval_in_routing():
    assert choose_route(_plan(approval=True), escalation_required=True) == "escalation"
    assert choose_route(_plan(approval=True), escalation_required=False) == "approval"
    assert choose_route(_plan(), escalation_required=False) == "low"


def test_token_usage_reducer_sums():
    total = merge_usage({"total_tokens": 5, "calls": 1}, {"total_tokens": 7, "calls": 1})
    assert total["total_tokens"] == 12 and total["calls"] == 2


def test_state_reducers_are_declared():
    hints = typing.get_type_hints(SupportState, include_extras=True)
    for key in ("errors", "completed_nodes", "token_usage"):
        assert typing.get_args(hints[key])[1:], f"{key} needs a reducer"


def test_classification_is_json_round_trippable():
    c = Classification(category=Category.BILLING, summary="x")
    assert Classification(**c.model_dump(mode="json")) == c
