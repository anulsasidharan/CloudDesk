"""The workflow graph (CLAUDE.md 7.3).

    understand_ticket -> classify_severity -> customer_context -> knowledge_retrieval
      -> troubleshooting -> resolution_planning -> risk_check
          |- escalation (policy)  -> escalation
          |- approval pending     -> human_approval (interrupt) -approved-> execute_resolution
          |                                                     `rejected-> escalation
          `- low risk             -> execute_resolution
      -> ticket_summary -> memory_update -> END

``risk_check`` writes a ``route`` ("low", "approval", "escalation"); ``ROUTE_TARGETS`` maps it to
the next node. ``human_approval`` pauses the run; ``route_after_approval`` reads the decision.
Both ``execute_resolution`` and ``escalation`` flow on to ``ticket_summary``.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.checkpointer import get_checkpointer
from agents.nodes import (
    classify_severity,
    customer_context,
    escalation,
    execute_resolution,
    human_approval,
    knowledge_retrieval,
    memory_update,
    resolution_planning,
    risk_check,
    ticket_summary,
    troubleshooting,
    understand_ticket,
)
from agents.risk import ROUTE_APPROVAL, ROUTE_ESCALATION, ROUTE_LOW
from agents.state import SupportState

NODES: dict[str, Any] = {
    "understand_ticket": understand_ticket,
    "classify_severity": classify_severity,
    "customer_context": customer_context,
    "knowledge_retrieval": knowledge_retrieval,
    "troubleshooting": troubleshooting,
    "resolution_planning": resolution_planning,
    "risk_check": risk_check,
    "human_approval": human_approval,
    "execute_resolution": execute_resolution,
    "escalation": escalation,
    "ticket_summary": ticket_summary,
    "memory_update": memory_update,
}

STRAIGHT_EDGES = [
    ("understand_ticket", "classify_severity"),
    ("classify_severity", "customer_context"),
    ("customer_context", "knowledge_retrieval"),
    ("knowledge_retrieval", "troubleshooting"),
    ("troubleshooting", "resolution_planning"),
    ("resolution_planning", "risk_check"),
    ("execute_resolution", "ticket_summary"),
    ("escalation", "ticket_summary"),
    ("ticket_summary", "memory_update"),
]

# Where each route goes after risk_check.
ROUTE_TARGETS = {
    ROUTE_LOW: "execute_resolution",
    ROUTE_APPROVAL: "human_approval",
    ROUTE_ESCALATION: "escalation",
}

# Where a human decision goes after human_approval: approved runs the actions, rejected escalates.
APPROVAL_TARGETS = {"approved": "execute_resolution", "rejected": "escalation"}

GRAPH_NODES = [*NODES]
GRAPH_EDGES = [
    *STRAIGHT_EDGES,
    *[("risk_check", target) for target in ROUTE_TARGETS.values()],
    *[("human_approval", target) for target in APPROVAL_TARGETS.values()],
    ("memory_update", END),
]


def route_after_risk(state: SupportState) -> str:
    return state.get("route", ROUTE_LOW)


def route_after_approval(state: SupportState) -> str:
    """Only an explicit ``approved`` runs the actions. Anything else is treated as a rejection."""
    return "approved" if state.get("approval_status") == "approved" else "rejected"


def build_graph(checkpointer: Any = None):
    """Compile the graph. Pass a checkpointer to make runs resumable by ``thread_id``."""
    graph = StateGraph(SupportState)
    for name, node in NODES.items():
        graph.add_node(name, node)
    graph.add_edge(START, "understand_ticket")
    for source, target in STRAIGHT_EDGES:
        graph.add_edge(source, target)
    graph.add_conditional_edges("risk_check", route_after_risk, ROUTE_TARGETS)
    graph.add_conditional_edges("human_approval", route_after_approval, APPROVAL_TARGETS)
    graph.add_edge("memory_update", END)
    return graph.compile(checkpointer=checkpointer)


_compiled: Any = None


async def get_graph():
    """The compiled graph with the process-wide checkpointer, built once."""
    global _compiled
    if _compiled is None:
        _compiled = build_graph(await get_checkpointer())
    return _compiled


def reset_graph() -> None:
    global _compiled
    _compiled = None
