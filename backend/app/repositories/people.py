"""Profiles, customers and everything that hangs off a customer."""

import hashlib

from sqlalchemy import select

from app.models.entities import (
    Customer,
    CustomerMemory,
    Profile,
    Subscription,
    Workspace,
)
from app.repositories.base import BaseRepository

MAX_RECALL = 10


class ProfileRepository(BaseRepository[Profile]):
    model = Profile

    async def get_by_email(self, email: str) -> Profile | None:
        stmt = select(Profile).where(Profile.email == email.strip().lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def first_with_role(self, role: str) -> Profile | None:
        stmt = select(Profile).where(Profile.role == role).order_by(Profile.email).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_email(self, email: str) -> Customer | None:
        stmt = select(Customer).where(Customer.email == email.strip().lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search(self, query: str = "", *, limit: int = 50, offset: int = 0) -> list[Customer]:
        stmt = select(Customer).order_by(Customer.name).limit(limit).offset(offset)
        if query.strip():
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                Customer.name.ilike(like) | Customer.company.ilike(like) | Customer.email.ilike(like)
            )
        return list((await self.session.execute(stmt)).scalars())


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription

    async def get_for_customer(self, customer_id: str) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(Subscription.customer_id == customer_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class WorkspaceRepository(BaseRepository[Workspace]):
    model = Workspace

    async def list_for_customer(self, customer_id: str) -> list[Workspace]:
        stmt = select(Workspace).where(Workspace.customer_id == customer_id).order_by(Workspace.name)
        return list((await self.session.execute(stmt)).scalars())


def content_hash(content: str) -> str:
    """Hash of whitespace-normalised, lower-cased text; the de-duplication key for notes."""
    normalised = " ".join(content.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class CustomerMemoryRepository(BaseRepository[CustomerMemory]):
    model = CustomerMemory

    async def add_note(
        self,
        customer_id: str,
        kind: str,
        content: str,
        *,
        source_ticket_id: str | None = None,
    ) -> CustomerMemory | None:
        """Store a note, or return ``None`` when an identical one exists.

        The caller is responsible for ``scrub()``-ing ``content`` first (Phase 11).
        """
        digest = content_hash(content)
        existing = await self.session.execute(
            select(CustomerMemory.id).where(
                CustomerMemory.customer_id == customer_id,
                CustomerMemory.kind == kind,
                CustomerMemory.content_hash == digest,
            )
        )
        if existing.first() is not None:
            return None
        return await self.add(
            customer_id=customer_id,
            kind=kind,
            content=content,
            content_hash=digest,
            source_ticket_id=source_ticket_id,
        )

    async def recall(self, customer_id: str, *, limit: int = MAX_RECALL) -> list[CustomerMemory]:
        stmt = (
            select(CustomerMemory)
            .where(CustomerMemory.customer_id == customer_id)
            .order_by(CustomerMemory.created_at.desc(), CustomerMemory.id)
            .limit(min(limit, MAX_RECALL))
        )
        return list((await self.session.execute(stmt)).scalars())
