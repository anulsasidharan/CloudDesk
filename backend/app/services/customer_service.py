"""Customer use cases (read side of F4)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import (
    CustomerMemoryRepository,
    CustomerRepository,
    SubscriptionRepository,
    TicketRepository,
    WorkspaceRepository,
)
from app.schemas.customers import CustomerDetail, CustomerPage
from app.schemas.records import CustomerMemoryOut, CustomerOut, SubscriptionOut, WorkspaceOut
from app.services.ticket_service import summaries

TICKET_LIMIT = 50


class CustomerNotFoundError(LookupError):
    pass


async def list_customers(
    session: AsyncSession, *, search: str, page: int, page_size: int
) -> CustomerPage:
    customers, total = await CustomerRepository(session).page(
        search, limit=page_size, offset=(page - 1) * page_size
    )
    return CustomerPage(
        items=[CustomerOut.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_customer(session: AsyncSession, customer_id: str) -> CustomerDetail:
    customer = await CustomerRepository(session).get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(customer_id)
    subscription = await SubscriptionRepository(session).get_for_customer(customer.id)
    workspaces = await WorkspaceRepository(session).list_for_customer(customer.id)
    tickets = await TicketRepository(session).history_for_customer(customer.id, limit=TICKET_LIMIT)
    memory = await CustomerMemoryRepository(session).recall(customer.id)
    return CustomerDetail(
        **CustomerOut.model_validate(customer).model_dump(),
        subscription=SubscriptionOut.model_validate(subscription) if subscription else None,
        workspaces=[WorkspaceOut.model_validate(w) for w in workspaces],
        tickets=await summaries(session, tickets),
        memory=[CustomerMemoryOut.model_validate(m) for m in memory],
    )
