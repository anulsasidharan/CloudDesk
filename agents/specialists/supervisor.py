"""Support Supervisor (F2, F3, F11): classify, rate severity, summarise. Rules first, model second."""

from __future__ import annotations

import re
import time

from app.core.guardrails import scan_for_injection, scrub
from app.core.llm import call_structured
from app.schemas.common import Category, Severity
from app.schemas.workflow import Classification, SeverityAssessment, TicketSummary

from agents import rules
from agents.prompts import (
    CLASSIFY_PROMPT,
    SEVERITY_PROMPT,
    SUMMARY_PROMPT,
    build_system,
    build_user,
)
from agents.specialists.base import AgentResult, elapsed_ms

MAX_SUMMARY_CHARS = 160


def one_line(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Single line, secrets scrubbed, trimmed to ``limit`` characters."""
    clean = " ".join(scrub(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


class SupervisorAgent:
    async def understand(self, subject: str, body: str) -> AgentResult[Classification]:
        """Category plus a one-line summary. A rule that has an opinion decides the category."""
        started = time.perf_counter()
        rule_category = rules.rule_category(f"{subject}\n{body}")

        def offline() -> Classification:
            return Classification(
                category=rule_category or rules.DEFAULT_CATEGORY,
                summary=one_line(subject),
                confidence=0.9 if rule_category else 0.4,
            )

        result = await call_structured(
            Classification,
            system=build_system(CLASSIFY_PROMPT),
            user=build_user(subject, body),
            offline=offline,
            agent="supervisor.understand",
        )
        model = result.output
        classification = Classification(
            category=rule_category or model.category,
            summary=one_line(model.summary) or one_line(subject),
            confidence=model.confidence,
            source="rules" if rule_category else "model",
        )
        return AgentResult(classification, result.usage, elapsed_ms(started))

    async def assess_severity(
        self,
        subject: str,
        body: str,
        category: Category | None = None,
        plan_name: str | None = None,
    ) -> AgentResult[SeverityAssessment]:
        """Severity with a reason. Rules raise the model's level, never lower it."""
        started = time.perf_counter()
        text = f"{subject}\n{body}"
        verdict = rules.rule_severity(text, category, plan_name)
        flagged = scan_for_injection(text).flagged

        def offline() -> SeverityAssessment:
            level = verdict.severity if verdict.matched else Severity.MEDIUM
            return SeverityAssessment(severity=level, reason=verdict.reason)

        facts = (
            f"Category: {category.value if category else 'unknown'}. "
            f"Plan: {plan_name or 'unknown'}."
        )
        result = await call_structured(
            SeverityAssessment,
            system=build_system(SEVERITY_PROMPT),
            user=build_user(subject, body, facts),
            offline=offline,
            agent="supervisor.severity",
        )
        final = rules.raise_severity(result.output.severity, verdict)
        reason = one_line(result.output.reason, 240)
        if verdict.matched and final is not result.output.severity:
            reason = f"{verdict.reason} (raised from {result.output.severity.value} by policy)"
        assessment = SeverityAssessment(
            severity=final,
            reason=reason or verdict.reason,
            rule_ids=list(verdict.rule_ids),
            injection_suspected=flagged,
        )
        return AgentResult(assessment, result.usage, elapsed_ms(started))

    async def summarize(
        self, subject: str, classification: Classification, plan_summary: str, outcome: str
    ) -> AgentResult[TicketSummary]:
        """The ``ticket_summary`` node (F11): built from our own outputs, never the raw body."""
        started = time.perf_counter()
        facts = (
            f"Subject: {subject}\nCategory: {classification.category.value}\n"
            f"Plan: {plan_summary}\nOutcome: {outcome}"
        )

        def offline() -> TicketSummary:
            return TicketSummary(
                summary=one_line(f"{classification.summary} Outcome: {outcome}. {plan_summary}", 400)
            )

        result = await call_structured(
            TicketSummary,
            system=build_system(SUMMARY_PROMPT),
            user=facts,  # system-generated text only, so nothing here is untrusted
            offline=offline,
            agent="supervisor.summary",
        )
        text = re.sub(r"\s+", " ", scrub(result.output.summary)).strip()
        return AgentResult(TicketSummary(summary=text), result.usage, elapsed_ms(started))
