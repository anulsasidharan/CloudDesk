"""The workflow graph (CLAUDE.md 7.3).

    understand_ticket -> classify_severity -> customer_context -> knowledge_retrieval
      -> troubleshooting -> resolution_planning -> risk_check -> execute_resolution
      -> ticket_summary -> memory_update -> END

``risk_check`` writes a ``route`` ("low", "approval", "escalation"). In this phase every route
continues to ``execute_resolution``, which runs only actions that need no approval and records
the rest as awaiting approval, so no money or account action can run. Phase 11 replaces
``ROUTE_TARGETS`` with the ``human_approval`` and ``escalation`` nodes; nothing else changes.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.checkpointer import get_checkpointer
from agents.nodes import (
    classify_severity,
    customer_context,
    execute_resolution,
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
    "execute_resolution": execute_resolution,
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
    ("ticket_summary", "memory_update"),
]

# Where each route goes after risk_check. Phase 11 points two of these at new nodes.
ROUTE_TARGETS = {
    ROUTE_LOW: "execute_resolution",
    ROUTE_APPROVAL: "execute_resolution",
    ROUTE_ESCALATION: "execute_resolution",
}

GRAPH_NODES = [*NODES]
GRAPH_EDGES = [
    *STRAIGHT_EDGES,
    *[("risk_check", target) for target in dict.fromkeys(ROUTE_TARGETS.values())],
    ("memory_update", END),
]


def route_after_risk(state: SupportState) -> str:
    return state.get("route", ROUTE_LOW)


def build_graph(checkpointer: Any = None):
    """Compile the graph. Pass a checkpointer to make runs resumable by ``thread_id``."""
    graph = StateGraph(SupportState)
    for name, node in NODES.items():
        graph.add_node(name, node)
    graph.add_edge(START, "understand_ticket")
    for source, target in STRAIGHT_EDGES:
        graph.add_edge(source, target)
    graph.add_conditional_edges("risk_check", route_after_risk, ROUTE_TARGETS)
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
