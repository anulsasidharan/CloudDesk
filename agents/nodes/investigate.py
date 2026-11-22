"""Investigate nodes: customer_context, knowledge_retrieval, troubleshooting (F4-F7)."""

from __future__ import annotations

from typing import Any

from agents.nodes.common import (
    cases_of,
    category_of,
    context_of,
    dump,
    evidence_of,
    finish,
    tracer_for,
)
from agents.specialists import CustomerAgent, KnowledgeAgent, TroubleshootingAgent
from agents.state import SupportState

CONTEXT = "customer_context"
KNOWLEDGE = "knowledge_retrieval"
TROUBLESHOOTING = "troubleshooting"


async def customer_context(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(CONTEXT):
        result = await CustomerAgent().run(state["customer_id"], state["ticket_id"])
        await tracer.tool_calls(CONTEXT, result.tool_calls)
    return finish(CONTEXT, {"customer_context": dump(result.output)})


async def knowledge_retrieval(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(KNOWLEDGE):
        result = await KnowledgeAgent().run(
            state["subject"], state["body"], category_of(state).value
        )
        await tracer.tool_calls(KNOWLEDGE, result.tool_calls)
    return finish(
        KNOWLEDGE,
        {
            "evidence": [dump(e) for e in result.output.evidence],
            "previous_cases": [dump(c) for c in result.output.previous_cases],
        },
    )


async def troubleshooting(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(TROUBLESHOOTING):
        result = await TroubleshootingAgent().run(
            state["subject"],
            state["body"],
            category_of(state),
            context_of(state),
            evidence_of(state),
            cases_of(state),
        )
        await tracer.tool_calls(TROUBLESHOOTING, result.tool_calls)
        await tracer.llm(TROUBLESHOOTING, result.usage, result.duration_ms, "diagnosis")
    return finish(TROUBLESHOOTING, {"diagnosis": dump(result.output)}, result.usage)
