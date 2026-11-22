"""Ticket use cases. Orchestrates repositories; knows nothing about HTTP."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthUser
from app.models.entities import Ticket, TicketMessage
from app.repositories import (
    ApprovalRepository,
    CustomerRepository,
    EscalationRepository,
    ProfileRepository,
    ResolutionActionRepository,
    SubscriptionRepository,
    TicketMessageRepository,
    TicketRepository,
    WorkflowEventRepository,
    WorkspaceRepository,
)
from app.schemas.common import EscalationStatus, SenderType, Severity, TicketStatus
from app.schemas.records import (
    CustomerOut,
    EscalationOut,
    ResolutionActionOut,
    SubscriptionOut,
    WorkspaceOut,
)
from app.schemas.tickets import (
    EscalateRequest,
    InfoRequest,
    ReplyCreate,
    TicketCreate,
    TicketDetail,
    TicketMessageOut,
    TicketOut,
    TicketPage,
    TicketPatch,
    TicketSummary,
    WorkflowEventOut,
)
from app.services import workflow_view

ESCALATION_TEAM = "support_leads"
HISTORY_LIMIT = 10


class TicketNotFoundError(LookupError):
    pass


class CustomerNotFoundError(LookupError):
    pass


class ProfileNotFoundError(LookupError):
    pass


class TicketClosedError(RuntimeError):
    """A customer-visible message cannot be sent on a closed ticket."""


async def summaries(session: AsyncSession, tickets: list[Ticket]) -> list[TicketSummary]:
    """Build summaries for many tickets with three batch queries (no per-row lookups)."""
    ids = [t.id for t in tickets]
    customers = await CustomerRepository(session).get_many(list({t.customer_id for t in tickets}))
    approvals = await ApprovalRepository(session).latest_status_by_ticket(ids)
    escalated = await EscalationRepository(session).ticket_ids_with_escalation(ids)
    return [
        TicketSummary(
            id=t.id,
            ticket_number=t.number,
            subject=t.subject,
            status=t.status,
            severity=t.severity,
            category=t.category,
            customer_id=t.customer_id,
            customer_name=customers[t.customer_id].name if t.customer_id in customers else "",
            channel=t.channel,
            created_at=t.created_at,
            updated_at=t.updated_at,
            escalation_required=t.id in escalated or t.status == TicketStatus.ESCALATED.value,
            approval_status=approvals.get(t.id, "not_required"),
        )
        for t in tickets
    ]


def _message_out(message: TicketMessage) -> TicketMessageOut:
    return TicketMessageOut(
        id=message.id,
        ticket_id=message.ticket_id,
        role=message.sender_type,
        author_name=message.sender_name,
        body=message.body,
        internal=message.is_internal,
        created_at=message.created_at,
    )


async def find_ticket(session: AsyncSession, ticket_ref: str) -> Ticket:
    """Find a ticket by id, or by number such as ``CD-1001``."""
    repo = TicketRepository(session)
    ticket = await repo.get(ticket_ref) or await repo.get_by_number(ticket_ref)
    if ticket is None:
        raise TicketNotFoundError(ticket_ref)
    return ticket


async def _out(session: AsyncSession, ticket: Ticket) -> TicketOut:
    (summary,) = await summaries(session, [ticket])
    return TicketOut(
        **summary.model_dump(),
        body=ticket.body,
        assigned_to=ticket.assigned_to,
        resolved_at=ticket.resolved_at,
        tags=[],
    )


async def _author_name(session: AsyncSession, caller: AuthUser) -> str:
    profile = await ProfileRepository(session).get(caller.id)
    return profile.full_name if profile else (caller.email or "Agent")


async def list_tickets(
    session: AsyncSession,
    *,
    status: str | None,
    severity: str | None,
    search: str | None,
    page: int,
    page_size: int,
) -> TicketPage:
    tickets, total = await TicketRepository(session).page(
        status=status,
        severity=severity,
        search=search,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return TicketPage(
        items=await summaries(session, tickets), total=total, page=page, page_size=page_size
    )


async def create_ticket(session: AsyncSession, data: TicketCreate) -> TicketOut:
    """Create the ticket and its first customer message. Does NOT start the workflow."""
    customer = await CustomerRepository(session).get(data.customer_id)
    if customer is None:
        raise CustomerNotFoundError(data.customer_id)
    tickets = TicketRepository(session)
    ticket = await tickets.add(
        number=await tickets.next_number(),
        customer_id=customer.id,
        subject=data.subject,
        body=data.body,
        channel=data.channel.value,
        status=TicketStatus.NEW.value,
    )
    await TicketMessageRepository(session).add(
        ticket_id=ticket.id,
        sender_type=SenderType.CUSTOMER.value,
        sender_name=customer.name,
        body=data.body,
    )
    return await _out(session, ticket)


async def get_ticket(session: AsyncSession, ticket_ref: str) -> TicketDetail:
    ticket = await find_ticket(session, ticket_ref)
    base = await _out(session, ticket)
    customer = await CustomerRepository(session).get(ticket.customer_id)
    if customer is None:  # FK makes this unreachable; keep the type checker honest
        raise CustomerNotFoundError(ticket.customer_id)
    messages = await TicketMessageRepository(session).list_for_ticket(ticket.id)
    history = await TicketRepository(session).history_for_customer(
        ticket.customer_id, exclude_ticket_id=ticket.id, limit=HISTORY_LIMIT
    )
    subscription = await SubscriptionRepository(session).get_for_customer(ticket.customer_id)
    workspaces = await WorkspaceRepository(session).list_for_customer(ticket.customer_id)
    actions = await ResolutionActionRepository(session).list_for_ticket(ticket.id)
    escalations = await EscalationRepository(session).list_for_ticket(ticket.id)
    return TicketDetail(
        **base.model_dump(),
        messages=[_message_out(m) for m in messages],
        customer=CustomerOut.model_validate(customer),
        subscription=SubscriptionOut.model_validate(subscription) if subscription else None,
        workspaces=[WorkspaceOut.model_validate(w) for w in workspaces],
        history=await summaries(session, history),
        workflow=await workflow_view.latest_view(session, ticket.id),
        resolution_actions=[
            ResolutionActionOut(
                id=a.id,
                ticket_id=a.ticket_id,
                workflow_id=a.workflow_id,
                tool=a.tool,
                arguments=a.args,
                status=a.status,
                result=a.result,
                requires_approval=a.requires_approval,
                created_at=a.created_at,
            )
            for a in actions
        ],
        escalation=EscalationOut.model_validate(escalations[-1]) if escalations else None,
    )


async def update_ticket(session: AsyncSession, ticket_ref: str, patch: TicketPatch) -> TicketOut:
    ticket = await find_ticket(session, ticket_ref)
    sent = patch.model_fields_set
    if "assigned_to" in sent:
        if (
            patch.assigned_to is not None
            and await ProfileRepository(session).get(patch.assigned_to) is None
        ):
            raise ProfileNotFoundError(patch.assigned_to)
        ticket.assigned_to = patch.assigned_to
    if patch.severity is not None:
        ticket.severity = patch.severity.value
    if patch.status is not None:
        await TicketRepository(session).set_status(ticket, patch.status)
    await session.flush()
    return await _out(session, ticket)


async def reply(
    session: AsyncSession, ticket_ref: str, data: ReplyCreate, caller: AuthUser
) -> TicketMessageOut:
    ticket = await find_ticket(session, ticket_ref)
    if not data.internal and ticket.status == TicketStatus.CLOSED.value:
        raise TicketClosedError(ticket.number)
    message = await TicketMessageRepository(session).add(
        ticket_id=ticket.id,
        sender_type=SenderType.AGENT.value,
        sender_name=await _author_name(session, caller),
        body=data.body,
        is_internal=data.internal,
    )
    if not data.internal and ticket.status == TicketStatus.NEW.value:
        await TicketRepository(session).set_status(ticket, TicketStatus.IN_PROGRESS)
    return _message_out(message)


async def request_info(
    session: AsyncSession, ticket_ref: str, data: InfoRequest, caller: AuthUser
) -> TicketMessageOut:
    ticket = await find_ticket(session, ticket_ref)
    if ticket.status == TicketStatus.CLOSED.value:
        raise TicketClosedError(ticket.number)
    body = "To help us resolve this, please tell us:\n" + "\n".join(
        f"{i}. {q}" for i, q in enumerate(data.questions, start=1)
    )
    message = await TicketMessageRepository(session).add(
        ticket_id=ticket.id,
        sender_type=SenderType.AGENT.value,
        sender_name=await _author_name(session, caller),
        body=body,
    )
    await TicketRepository(session).set_status(ticket, TicketStatus.WAITING_ON_CUSTOMER)
    return _message_out(message)


async def escalate(session: AsyncSession, ticket_ref: str, data: EscalateRequest) -> EscalationOut:
    ticket = await find_ticket(session, ticket_ref)
    severity = Severity.CRITICAL if data.priority == "urgent" else Severity.HIGH
    escalation = await EscalationRepository(session).add(
        ticket_id=ticket.id,
        team=ESCALATION_TEAM,
        reason=data.reason,
        severity=severity.value,
        status=EscalationStatus.OPEN.value,
    )
    await TicketRepository(session).set_status(ticket, TicketStatus.ESCALATED)
    return EscalationOut.model_validate(escalation)


async def list_events(session: AsyncSession, ticket_ref: str) -> list[WorkflowEventOut]:
    ticket = await find_ticket(session, ticket_ref)
    events = await WorkflowEventRepository(session).list_for_ticket(ticket.id)
    return [
        WorkflowEventOut(
            id=e.id,
            workflow_id=e.workflow_id,
            ticket_id=e.ticket_id,
            event_type=e.event_type,
            node=e.node,
            tool=e.payload.get("tool"),
            message=str(e.payload.get("message", "")),
            duration_ms=e.duration_ms,
            payload=e.payload,
            created_at=e.created_at,
        )
        for e in events
    ]
