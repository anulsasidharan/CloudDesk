"""Read-only tools. None of them writes anything and none needs approval."""

from typing import Any

from langchain_core.tools import tool

from app.repositories import (
    CustomerRepository,
    IncidentRepository,
    SubscriptionRepository,
    TicketRepository,
)
from app.tools.base import tool_session
from rag.retriever import retrieve


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


@tool
async def get_customer(customer_id: str) -> dict[str, Any]:
    """Look up a customer by id or email: name, company, plan, status and timezone."""
    async with tool_session() as session:
        repo = CustomerRepository(session)
        customer = await repo.get(customer_id) or await repo.get_by_email(customer_id)
        if customer is None:
            raise LookupError(f"customer not found: {customer_id}")
        return {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "company": customer.company,
            "plan": customer.plan,
            "status": customer.status,
            "timezone": customer.timezone,
        }


@tool
async def get_subscription(customer_id: str) -> dict[str, Any]:
    """Get the customer's current subscription: plan, seats, price, storage and API limits."""
    async with tool_session() as session:
        sub = await SubscriptionRepository(session).get_for_customer(customer_id)
        if sub is None:
            raise LookupError(f"no subscription for customer: {customer_id}")
        return {
            "id": sub.id,
            "plan": sub.plan,
            "status": sub.status,
            "billing_cycle": sub.billing_cycle,
            "seats_purchased": sub.seats_purchased,
            "seats_used": sub.seats_used,
            "seat_price": sub.seat_price,
            "currency": sub.currency,
            "storage_limit_gb": sub.storage_limit_gb,
            "storage_used_gb": sub.storage_used_gb,
            "api_rate_limit_per_minute": sub.api_rate_limit_per_minute,
            "renews_at": _iso(sub.renews_at),
        }


@tool
async def get_ticket_history(
    customer_id: str, exclude_ticket_id: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """List the customer's most recent tickets (newest first), optionally skipping one ticket."""
    async with tool_session() as session:
        tickets = await TicketRepository(session).history_for_customer(
            customer_id, exclude_ticket_id=exclude_ticket_id, limit=max(1, min(limit, 25))
        )
        return {
            "tickets": [
                {
                    "id": t.id,
                    "number": t.number,
                    "subject": t.subject,
                    "status": t.status,
                    "category": t.category,
                    "severity": t.severity,
                }
                for t in tickets
            ]
        }


@tool
async def search_docs(query: str, category: str | None = None, top_k: int = 3) -> dict[str, Any]:
    """Search the knowledge base (semantic plus keyword) and return cited evidence."""
    evidence = await retrieve(query, category_hint=category, top_k=max(1, min(top_k, 10)))
    return {"evidence": [item.to_dict() for item in evidence]}


@tool
async def check_service_status(service: str | None = None) -> dict[str, Any]:
    """Report active incidents, optionally for one service (for example sso, api, storage)."""
    async with tool_session() as session:
        incidents = await IncidentRepository(session).active(service)
        return {
            "service": service,
            "operational": not incidents,
            "incidents": [
                {
                    "id": i.id,
                    "title": i.title,
                    "service": i.service,
                    "severity": i.severity,
                    "started_at": _iso(i.started_at),
                }
                for i in incidents
            ],
        }


READ_ONLY_TOOLS = [
    get_customer,
    get_subscription,
    get_ticket_history,
    search_docs,
    check_service_status,
]
