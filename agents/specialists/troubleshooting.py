"""Troubleshooting Agent (F7): probable causes and numbered steps, grounded in facts we hold."""

from __future__ import annotations

import time

from app.core.llm import call_structured
from app.schemas.common import Category
from app.schemas.workflow import (
    CustomerContext,
    Diagnosis,
    EvidenceItem,
    PreviousCase,
    ToolCallRecord,
)
from app.tools import ToolRegistry

from agents.prompts import DIAGNOSIS_PROMPT, build_system, build_user
from agents.specialists.base import AgentResult, elapsed_ms, run_tool

MAX_STEPS = 6

#: Which service to check for an active incident, per category. No entry = nothing to check.
SERVICE_FOR_CATEGORY: dict[Category, str] = {
    Category.LOGIN_ISSUE: "sso",
    Category.API_FAILURE: "api",
    Category.STORAGE_QUOTA: "storage",
    Category.INTEGRATION: "integrations",
}

#: (probable causes, steps) per category. Deterministic and easy to review.
PLAYBOOKS: dict[Category, tuple[list[str], list[str]]] = {
    Category.LOGIN_ISSUE: (
        ["Identity provider or SSO configuration problem", "MFA or password lockout"],
        [
            "Check whether there is an active sign-in incident",
            "Confirm the sign-in method the user uses (SSO, password or MFA)",
            "Ask the user to retry in a private window after clearing cookies",
            "If MFA is locked, follow the backup-code recovery process",
        ],
    ),
    Category.BILLING: (
        ["Seats billed do not match seats in use", "Charge is from a renewal or add-on"],
        [
            "Compare seats purchased with seats in use",
            "Review the latest invoice and the refund policy",
            "Submit any refund for human approval",
            "Confirm the outcome to the customer",
        ],
    ),
    Category.API_FAILURE: (
        ["Request rate is above the plan limit", "Credentials are invalid or expired"],
        [
            "Check the plan's API rate limit against the call volume",
            "Read the Retry-After header on the 429 response",
            "Add exponential backoff and spread calls over a longer window",
        ],
    ),
    Category.WORKSPACE_PERMISSIONS: (
        ["Sharing is restricted by the plan or the workspace setting"],
        [
            "Check the plan and the workspace sharing setting",
            "Explain what the plan allows",
            "Offer a view-only guest link or an upgrade if sharing is required",
        ],
    ),
    Category.STORAGE_QUOTA: (
        ["Storage used is at or near the plan limit"],
        [
            "Compare storage used with the plan limit",
            "Suggest clearing old file versions",
            "Explain the storage add-on or a plan upgrade",
        ],
    ),
    Category.INTEGRATION: (
        ["The integration connection or target channel changed"],
        [
            "Open the integration settings and check the connection",
            "Reconnect the integration and re-select the channel",
            "Send a test notification",
        ],
    ),
    Category.FEATURE_REQUEST: (
        ["Not a fault: a request for new behaviour"],
        [
            "Thank the customer",
            "Log the request on the roadmap",
            "Share the public voting page",
        ],
    ),
    Category.ACCOUNT: (
        ["Account or data change that needs the privacy team"],
        [
            "Verify the requester is an owner or admin of the account",
            "Explain the retention and erasure process",
            "Hand over to the privacy team before any deletion",
        ],
    ),
    Category.SECURITY: (
        ["Possible unauthorised access to an account"],
        [
            "Ask the customer to reset passwords and sign out all sessions",
            "Require MFA for the affected accounts",
            "Hand over to the security team to review the sign-in logs",
        ],
    ),
    Category.OTHER: (
        ["Not enough detail yet to name a cause"],
        [
            "Ask the customer for the exact error message and time",
            "Check the file recovery and version history options",
            "Check the status page for active incidents",
        ],
    ),
}


def _facts_causes(
    category: Category, context: CustomerContext, status: dict | None
) -> tuple[list[str], list[str]]:
    """Causes and steps that come from the customer's own numbers and any active incident."""
    causes: list[str] = []
    steps: list[str] = []
    if status and status.get("incidents"):
        causes.append(f"Active incident: {status['incidents'][0]['title']}")
        steps.append("Share the incident status with the customer and promise an update")
    sub = context.subscription or {}
    if category is Category.STORAGE_QUOTA and sub.get("storage_limit_gb"):
        used, limit = sub.get("storage_used_gb", 0), sub["storage_limit_gb"]
        if used >= 0.9 * limit:
            causes.append(f"Storage is {used:g} GB of {limit} GB, above 90% of the plan limit")
    if category is Category.BILLING:
        bought, in_use = sub.get("seats_purchased", 0), sub.get("seats_used", 0)
        if bought > in_use:
            causes.append(f"{bought} seats are billed but {in_use} are in use")
    if category is Category.API_FAILURE and sub.get("api_rate_limit_per_minute"):
        causes.append(f"Plan limit is {sub['api_rate_limit_per_minute']} requests per minute")
    return causes, steps


class TroubleshootingAgent:
    async def run(
        self,
        subject: str,
        body: str,
        category: Category,
        context: CustomerContext,
        evidence: list[EvidenceItem] | None = None,
        previous_cases: list[PreviousCase] | None = None,
        registry: ToolRegistry | None = None,
    ) -> AgentResult[Diagnosis]:
        started = time.perf_counter()
        calls: list[ToolCallRecord] = []

        status: dict | None = None
        service = SERVICE_FOR_CATEGORY.get(category)
        if service:
            check = await run_tool(registry, "check_service_status", {"service": service}, calls)
            status = check.data if check.ok else None

        fact_causes, fact_steps = _facts_causes(category, context, status)
        base_causes, base_steps = PLAYBOOKS.get(category, PLAYBOOKS[Category.OTHER])
        case_steps = next((c.steps for c in (previous_cases or []) if c.category == category.value), [])

        def offline() -> Diagnosis:
            steps = list(dict.fromkeys([*fact_steps, *base_steps, *case_steps]))[:MAX_STEPS]
            return Diagnosis(
                probable_causes=[*fact_causes, *base_causes],
                steps=steps,
                service_status=status,
                confidence=0.8 if fact_causes else 0.6,
            )

        titles = "; ".join(e.title for e in (evidence or [])) or "none"
        facts = (
            f"Category: {category.value}. Articles: {titles}. "
            f"Active incidents: {len((status or {}).get('incidents', []))}."
        )
        result = await call_structured(
            Diagnosis,
            system=build_system(DIAGNOSIS_PROMPT),
            user=build_user(subject, body, facts),
            offline=offline,
            agent="troubleshooting",
        )
        diagnosis = result.output.model_copy(update={"service_status": status})
        diagnosis.steps = diagnosis.steps[:MAX_STEPS]
        return AgentResult(diagnosis, result.usage, elapsed_ms(started), calls)
