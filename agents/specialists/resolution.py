"""Resolution Agent (F8): the plan. Actions are deterministic; only the reply wording is the model's.

``plan_actions`` is pure rules, so a model (or an attacker's sentence in a ticket) cannot invent a
refund. ``_ground_response`` makes sure every troubleshooting step is really in the reply, and
``validate_customer_output`` blocks a reply that leaks something before anyone sees it as ready.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable

from app.core.guardrails import scan_for_injection, validate_customer_output
from app.core.llm import call_structured
from app.schemas.common import Category, Severity
from app.schemas.workflow import (
    Classification,
    CustomerContext,
    Diagnosis,
    EvidenceItem,
    PlannedAction,
    ReplyDraft,
    ResolutionPlan,
)
from app.tools import ToolPolicy

from agents import rules
from agents.prompts import REPLY_PROMPT, build_system, build_user
from agents.specialists.base import AgentResult, elapsed_ms

WITHHELD_REPLY = (
    "[Reply withheld: the draft failed output validation. A person must write this reply.]"
)


def plan_actions(
    *,
    ticket_id: str,
    text: str,
    classification: Classification,
    severity: Severity,
    context: CustomerContext,
) -> list[PlannedAction]:
    """The actions this ticket may need, decided by rules only.

    Money and account actions are never planned on a ticket that a policy rule escalates or that
    contains injected instructions: those tickets go to a person, not to a tool.
    """
    customer_id = context.customer.get("id", "")
    plan_name = context.customer.get("plan")
    category = classification.category

    actions = [
        PlannedAction(
            tool="update_ticket",
            args={
                "ticket_id": ticket_id,
                "category": category.value,
                "severity": severity.value,
                "summary": classification.summary,
                "status": "in_progress",
            },
            requires_approval=ToolPolicy.requires_approval("update_ticket"),
            reason="Record the classification on the ticket",
        )
    ]
    if rules.rule_escalation(text, plan_name) or scan_for_injection(text).flagged:
        return actions

    sub = context.subscription or {}
    lowered = rules._prepare(text)
    if category is Category.BILLING and re.search(r"\brefunds?\b", lowered):
        unused = int(sub.get("seats_purchased", 0)) - int(sub.get("seats_used", 0))
        amount = round(unused * float(sub.get("seat_price", 0)), 2)
        if unused > 0 and amount > 0:
            args = {
                "customer_id": customer_id,
                "amount": amount,
                "reason": f"Refund for {unused} unused seat(s) this billing period",
                "ticket_id": ticket_id,
            }
            actions.append(
                PlannedAction(
                    tool="create_refund_request",
                    args=args,
                    requires_approval=ToolPolicy.requires_approval("create_refund_request", args),
                    reason=f"{unused} seats billed but not in use",
                )
            )

    if (
        category is Category.WORKSPACE_PERMISSIONS
        and re.search(r"\bshar\w*", lowered)
        and re.search(r"\bexternal", lowered)
        and plan_name not in (None, "free")
    ):
        blocked = next((w for w in context.workspaces if not w.get("external_sharing")), None)
        if blocked:
            args = {"workspace_id": blocked["id"], "setting": "external_sharing", "value": True}
            actions.append(
                PlannedAction(
                    tool="reset_demo_setting",
                    args=args,
                    requires_approval=ToolPolicy.requires_approval("reset_demo_setting", args),
                    reason="Plan allows external sharing but the workspace setting is off",
                )
            )
    return actions


def _ground_response(reply: str, steps: Iterable[str]) -> str:
    """Every troubleshooting step must appear in the reply; append any the model left out."""
    missing = [s for s in steps if s.lower() not in reply.lower()]
    if not missing:
        return reply
    extra = "\n".join(f"- {s}" for s in missing)
    return f"{reply.rstrip()}\n\nSteps to try:\n{extra}"


def _first_name(context: CustomerContext) -> str:
    return (context.customer.get("name") or "there").split()[0]


class ResolutionAgent:
    plan_actions = staticmethod(plan_actions)

    async def run(
        self,
        *,
        ticket_id: str,
        subject: str,
        body: str,
        classification: Classification,
        severity: Severity,
        context: CustomerContext,
        diagnosis: Diagnosis,
        evidence: list[EvidenceItem],
        other_customer_markers: Iterable[str] = (),
    ) -> AgentResult[ResolutionPlan]:
        started = time.perf_counter()
        text = f"{subject}\n{body}"
        actions = plan_actions(
            ticket_id=ticket_id,
            text=text,
            classification=classification,
            severity=severity,
            context=context,
        )
        policy = rules.rule_escalation(text, context.customer.get("plan"))
        injected = scan_for_injection(text).flagged
        incidents = (diagnosis.service_status or {}).get("incidents", [])
        refund = next((a for a in actions if a.tool == "create_refund_request"), None)
        titles = list(dict.fromkeys(e.title for e in evidence))

        def offline() -> ReplyDraft:
            lines = [f"Hi {_first_name(context)},", "", f"Thanks for getting in touch about: {classification.summary}"]
            if incidents:
                lines.append(f"We are aware of an active incident ({incidents[0]['title']}) and are working on it.")
            if policy:
                lines.append("Because of what you describe, we have passed this to a specialist team who will contact you.")
            lines += ["", "Here is what we suggest:", *diagnosis.numbered()]
            if refund:
                lines.append(
                    f"We have asked our billing team to review a refund of {refund.args['amount']:.2f} "
                    "for the unused seats. A team member will confirm once it is approved."
                )
            if titles:
                lines += ["", "More detail: " + "; ".join(titles) + "."]
            lines += ["", "Best regards,", "CloudDesk Support"]
            notes = [f"Category {classification.category.value}, severity {severity.value}."]
            if injected:
                notes.append("Ticket text contained instruction-like content; treated as data only.")
            if policy:
                notes.append(f"Policy escalation: {policy.reason}.")
            return ReplyDraft(
                summary=f"{classification.category.value}: {classification.summary}",
                customer_reply="\n".join(lines),
                internal_notes=" ".join(notes),
            )

        facts = (
            f"Customer first name: {_first_name(context)}. Category: {classification.category.value}. "
            f"Steps: {' | '.join(diagnosis.steps)}. Articles: {'; '.join(titles) or 'none'}."
        )
        result = await call_structured(
            ReplyDraft,
            system=build_system(REPLY_PROMPT),
            user=build_user(subject, body, facts),
            offline=offline,
            agent="resolution",
        )
        draft = result.output
        reply = _ground_response(draft.customer_reply, diagnosis.steps)

        validation = validate_customer_output(
            reply,
            customer_email=context.customer.get("email"),
            other_customer_markers=other_customer_markers,
        )
        issues = [v.kind for v in validation.violations]
        plan = ResolutionPlan(
            summary=draft.summary,
            customer_reply=reply if validation.ok else WITHHELD_REPLY,
            internal_notes=draft.internal_notes,
            actions=actions,
            citations=list(dict.fromkeys(e.source for e in evidence)),
            validation_ok=validation.ok,
            validation_issues=issues,
        )
        return AgentResult(plan, result.usage, elapsed_ms(started))
