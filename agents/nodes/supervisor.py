"""Supervisor nodes: understand_ticket, classify_severity, ticket_summary (F2, F3, F11)."""

from __future__ import annotations

from typing import Any

from app.core import database
from app.repositories import TicketRepository
from app.schemas.common import Category

from agents.nodes.common import classification_of, dump, finish, plan_of, tracer_for
from agents.specialists import SupervisorAgent
from agents.state import SupportState

UNDERSTAND = "understand_ticket"
SEVERITY = "classify_severity"
SUMMARY = "ticket_summary"


async def understand_ticket(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(UNDERSTAND):
        result = await SupervisorAgent().understand(state["subject"], state["body"])
        await tracer.llm(UNDERSTAND, result.usage, result.duration_ms, "classification")
    return finish(UNDERSTAND, {"classification": dump(result.output)}, result.usage)


async def classify_severity(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(SEVERITY):
        category = Category(state["classification"]["category"])
        result = await SupervisorAgent().assess_severity(
            state["subject"], state["body"], category, state.get("plan_name")
        )
        await tracer.llm(SEVERITY, result.usage, result.duration_ms, "severity")
    assessment = result.output
    return finish(
        SEVERITY,
        {
            "severity": assessment.severity.value,
            "severity_reason": assessment.reason,
            "rule_ids": assessment.rule_ids,
            "injection_suspected": assessment.injection_suspected,
        },
        result.usage,
    )


def _outcome(state: SupportState) -> str:
    route = state.get("route", "low")
    if route == "escalation":
        return "policy escalation needed, held for a person"
    if route == "approval":
        return "waiting for human approval"
    return "reply drafted for agent review"


async def ticket_summary(state: SupportState) -> dict[str, Any]:
    tracer = tracer_for(state)
    async with tracer.node(SUMMARY):
        plan = plan_of(state)
        result = await SupervisorAgent().summarize(
            state["subject"], classification_of(state), plan.summary, _outcome(state)
        )
        await tracer.llm(SUMMARY, result.usage, result.duration_ms, "summary")
        # The summary and severity reason live on the ticket so list screens can show them.
        async with database.session_scope() as session:
            ticket = await TicketRepository(session).get(state["ticket_id"])
            if ticket is not None:
                ticket.summary = result.output.summary
                ticket.severity_reason = state.get("severity_reason")
    return finish(SUMMARY, {"ticket_summary": result.output.summary}, result.usage)
