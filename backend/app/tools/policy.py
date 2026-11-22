"""ToolPolicy: which tools may run unattended. Deterministic, never decided by a model."""

from collections.abc import Mapping
from typing import Any

from app.core.config import get_settings

# Tools that only read, or that are the safe path (escalation).
NO_APPROVAL_TOOLS = frozenset(
    {
        "get_customer",
        "get_subscription",
        "get_ticket_history",
        "search_docs",
        "check_service_status",
        "update_ticket",
        "create_escalation",
    }
)
# Tools that touch money or an account. Always gated.
ALWAYS_APPROVAL_TOOLS = frozenset({"reset_demo_setting"})


class ToolPolicy:
    """Decides ``requires_approval`` for a tool call. Unknown tools always require approval."""

    @staticmethod
    def requires_approval(name: str, args: Mapping[str, Any] | None = None) -> bool:
        if name in ALWAYS_APPROVAL_TOOLS:
            return True
        if name == "create_refund_request":
            settings = get_settings()
            if settings.approval_required_for_refunds:
                return True
            try:
                amount = float((args or {}).get("amount", 0))
            except (TypeError, ValueError):
                return True
            return amount > settings.max_refund_without_approval
        return name not in NO_APPROVAL_TOOLS
