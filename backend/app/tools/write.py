"""Write tools. Money and account changes are approval-gated by ``ToolPolicy`` in the registry.

These functions assume the registry already checked approval. Never call them directly.
"""

from typing import Any

from langchain_core.tools import tool

from app.repositories import (
    EscalationRepository,
    SubscriptionRepository,
    TicketRepository,
    WorkspaceRepository,
)
from app.schemas.common import Category, Severity, TicketStatus
from app.tools.base import tool_session
from integrations.factory import get_billing, get_notifications, get_workspace_admin

# Settings a support agent may reset. Anything else is refused.
RESETTABLE_SETTINGS = ("external_sharing", "mfa_required", "sso_enabled")


@tool
async def update_ticket(
    ticket_id: str,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Update a ticket's status, category, severity or one-line summary."""
    async with tool_session() as session:
        repo = TicketRepository(session)
        ticket = await repo.get(ticket_id)
        if ticket is None:
            raise LookupError(f"ticket not found: {ticket_id}")
        if category is not None:
            ticket.category = Category(category).value
        if severity is not None:
            ticket.severity = Severity(severity).value
        if summary is not None:
            ticket.summary = summary
        if status is not None:
            await repo.set_status(ticket, TicketStatus(status))
        await session.flush()
        return {
            "ticket_id": ticket.id,
            "status": ticket.status,
            "category": ticket.category,
            "severity": ticket.severity,
        }


@tool
async def create_escalation(
    ticket_id: str, team: str, reason: str, severity: str = "high", workflow_id: str | None = None
) -> dict[str, Any]:
    """Escalate a ticket to a named internal team and notify them. This is the safe path."""
    async with tool_session() as session:
        if await TicketRepository(session).get(ticket_id) is None:
            raise LookupError(f"ticket not found: {ticket_id}")
        escalation = await EscalationRepository(session).add(
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            team=team,
            reason=reason,
            severity=Severity(severity).value,
        )
        note = await get_notifications().notify_team(team=team, message=reason)
        return {
            "escalation_id": escalation.id,
            "team": team,
            "notification_id": note["notification_id"],
        }


@tool
async def create_refund_request(
    customer_id: str, amount: float, reason: str, ticket_id: str | None = None
) -> dict[str, Any]:
    """Request a refund for a customer. Approval required: it moves money."""
    if amount <= 0:
        raise ValueError("refund amount must be greater than zero")
    async with tool_session() as session:
        sub = await SubscriptionRepository(session).get_for_customer(customer_id)
        currency = sub.currency if sub else "USD"
    refund = await get_billing().create_refund(
        customer_id=customer_id, amount=amount, currency=currency, reason=reason
    )
    return {**refund, "ticket_id": ticket_id}


@tool
async def reset_demo_setting(
    workspace_id: str, setting: str, value: bool = False
) -> dict[str, Any]:
    """Reset one workspace setting (external_sharing, mfa_required, sso_enabled). Approval required."""
    if setting not in RESETTABLE_SETTINGS:
        raise ValueError(f"setting not resettable: {setting}")
    async with tool_session() as session:
        workspace = await WorkspaceRepository(session).get(workspace_id)
        if workspace is None:
            raise LookupError(f"workspace not found: {workspace_id}")
        change = await get_workspace_admin().reset_setting(
            workspace_id=workspace_id, setting=setting, value=value
        )
        setattr(workspace, setting, value)
        await session.flush()
        return change


WRITE_TOOLS = [update_ticket, create_escalation, create_refund_request, reset_demo_setting]
