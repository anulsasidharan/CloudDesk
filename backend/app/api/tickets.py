"""``/tickets`` routes. HTTP, auth and RBAC only; the work happens in ``ticket_service``.

``/run`` and ``/workflow`` arrive with the workflow in Phase 10.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import AuthUser, require_role
from app.schemas.common import Role, Severity, TicketStatus
from app.schemas.records import EscalationOut
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
    WorkflowEventOut,
)
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])
VIEWER = Depends(require_role(Role.VIEWER))
AGENT = Depends(require_role(Role.AGENT))
STATUS_QUERY = Query(None, alias="status")


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")


@router.get("", response_model=TicketPage)
async def list_tickets(
    status_: TicketStatus | None = STATUS_QUERY,
    severity: Severity | None = None,
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> TicketPage:
    return await ticket_service.list_tickets(
        session,
        status=status_.value if status_ else None,
        severity=severity.value if severity else None,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    _: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> TicketOut:
    try:
        return await ticket_service.create_ticket(session, body)
    except ticket_service.CustomerNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found") from exc


@router.get("/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: str,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> TicketDetail:
    try:
        return await ticket_service.get_ticket(session, ticket_id)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{ticket_id}", response_model=TicketOut)
async def patch_ticket(
    ticket_id: str,
    body: TicketPatch,
    _: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> TicketOut:
    if not body.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nothing to update")
    try:
        return await ticket_service.update_ticket(session, ticket_id, body)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc
    except ticket_service.ProfileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignee not found") from exc


@router.get("/{ticket_id}/events", response_model=list[WorkflowEventOut])
async def ticket_events(
    ticket_id: str,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> list[WorkflowEventOut]:
    try:
        return await ticket_service.list_events(session, ticket_id)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc


@router.post(
    "/{ticket_id}/reply", response_model=TicketMessageOut, status_code=status.HTTP_201_CREATED
)
async def reply(
    ticket_id: str,
    body: ReplyCreate,
    caller: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> TicketMessageOut:
    try:
        return await ticket_service.reply(session, ticket_id, body, caller)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc
    except ticket_service.TicketClosedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed") from exc


@router.post(
    "/{ticket_id}/request-info",
    response_model=TicketMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_info(
    ticket_id: str,
    body: InfoRequest,
    caller: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> TicketMessageOut:
    try:
        return await ticket_service.request_info(session, ticket_id, body, caller)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc
    except ticket_service.TicketClosedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed") from exc


@router.post(
    "/{ticket_id}/escalate", response_model=EscalationOut, status_code=status.HTTP_201_CREATED
)
async def escalate(
    ticket_id: str,
    body: EscalateRequest,
    _: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> EscalationOut:
    try:
        return await ticket_service.escalate(session, ticket_id, body)
    except ticket_service.TicketNotFoundError as exc:
        raise _not_found() from exc
