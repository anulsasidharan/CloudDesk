"""Tickets and their messages."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.entities import Ticket, TicketMessage
from app.repositories.base import BaseRepository
from app.schemas.common import TicketStatus

TICKET_PREFIX = "CD-"
FIRST_TICKET_NUMBER = 1001


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    async def get_by_number(self, number: str) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.number == number.strip().upper())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def next_number(self) -> str:
        """Next ``CD-####``. The unique constraint backstops a concurrent insert."""
        numbers = (await self.session.execute(select(Ticket.number))).scalars()
        highest = max(
            (int(n[len(TICKET_PREFIX) :]) for n in numbers if n[len(TICKET_PREFIX) :].isdigit()),
            default=FIRST_TICKET_NUMBER - 1,
        )
        return f"{TICKET_PREFIX}{highest + 1}"

    async def list_filtered(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        customer_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Ticket]:
        stmt = select(Ticket).order_by(Ticket.number).limit(limit).offset(offset)
        for column, value in (
            (Ticket.status, status),
            (Ticket.severity, severity),
            (Ticket.category, category),
            (Ticket.customer_id, customer_id),
        ):
            if value:
                stmt = stmt.where(column == value)
        return list((await self.session.execute(stmt)).scalars())

    async def history_for_customer(
        self, customer_id: str, *, exclude_ticket_id: str | None = None, limit: int = 10
    ) -> list[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.customer_id == customer_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        if exclude_ticket_id:
            stmt = stmt.where(Ticket.id != exclude_ticket_id)
        return list((await self.session.execute(stmt)).scalars())

    async def counts_by_status(self) -> dict[str, int]:
        stmt = select(Ticket.status, func.count()).group_by(Ticket.status)
        return {status: int(n) for status, n in (await self.session.execute(stmt)).all()}

    async def set_status(self, ticket: Ticket, status: TicketStatus) -> Ticket:
        ticket.status = status.value
        if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return ticket


class TicketMessageRepository(BaseRepository[TicketMessage]):
    model = TicketMessage

    async def list_for_ticket(self, ticket_id: str) -> list[TicketMessage]:
        stmt = (
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at, TicketMessage.id)
        )
        return list((await self.session.execute(stmt)).scalars())
