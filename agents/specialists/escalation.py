"""Escalation Agent (F10): policy rules ALWAYS win; the model only judges grey areas.

    matched = rules.rule_escalation(...)            # policy
    result  = await call_structured(...)            # judgement
    if matched:  decision = policy decision
    elif the model wants to escalate and (severity is high or critical AND it is unsure): keep it
    else:        no escalation (a vague model escalation is distrusted)
"""

from __future__ import annotations

import time

from app.core.llm import call_structured
from app.schemas.common import Severity
from app.schemas.workflow import EscalationDecision, ToolCallRecord
from app.tools import ToolRegistry

from agents import rules
from agents.prompts import ESCALATION_PROMPT, build_system, build_user
from agents.specialists.base import AgentResult, elapsed_ms, run_tool

LOW_CONFIDENCE = 0.5
DEFAULT_TEAM = "support_leads"
SERIOUS = (Severity.HIGH, Severity.CRITICAL)


class EscalationAgent:
    async def run(
        self,
        subject: str,
        body: str,
        plan_name: str | None = None,
        severity: Severity = Severity.MEDIUM,
    ) -> AgentResult[EscalationDecision]:
        started = time.perf_counter()
        policy = rules.rule_escalation(f"{subject}\n{body}", plan_name)

        def offline() -> EscalationDecision:
            # Offline the model never volunteers an escalation: rules are the only trigger.
            return EscalationDecision(escalation_required=False, confidence=0.8)

        result = await call_structured(
            EscalationDecision,
            system=build_system(ESCALATION_PROMPT),
            user=build_user(subject, body, f"Severity: {severity.value}. Plan: {plan_name}."),
            offline=offline,
            agent="escalation",
        )
        model = result.output

        if policy:
            decision = EscalationDecision(
                escalation_required=True,
                team=policy.team,
                reason=policy.reason,
                severity=policy.severity,
                policy_matched=True,
                rule_ids=list(policy.rule_ids),
                confidence=1.0,
            )
        elif model.escalation_required and severity in SERIOUS and model.confidence < LOW_CONFIDENCE:
            decision = model.model_copy(
                update={"team": model.team or DEFAULT_TEAM, "severity": severity, "policy_matched": False}
            )
        else:
            decision = EscalationDecision(
                escalation_required=False,
                reason="No policy rule matched",
                severity=severity,
                confidence=model.confidence,
            )
        return AgentResult(decision, result.usage, elapsed_ms(started))

    async def file(
        self,
        decision: EscalationDecision,
        ticket_id: str,
        workflow_id: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> AgentResult[dict]:
        """Record the escalation and notify the team, through ``ToolRegistry`` (the safe path)."""
        started = time.perf_counter()
        calls: list[ToolCallRecord] = []
        if not decision.escalation_required or not decision.team:
            return AgentResult({}, duration_ms=elapsed_ms(started))
        result = await run_tool(
            registry,
            "create_escalation",
            {
                "ticket_id": ticket_id,
                "team": decision.team,
                "reason": decision.reason,
                "severity": decision.severity.value,
                "workflow_id": workflow_id,
            },
            calls,
        )
        return AgentResult(result.data or {}, duration_ms=elapsed_ms(started), tool_calls=calls)
