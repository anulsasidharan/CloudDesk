"""Phase 2: repositories against a private in-memory SQLite database loaded with the demo data."""

import pytest
from app.core.database import enable_sqlite_foreign_keys
from app.models.base import Base
from app.repositories import (
    ApprovalRepository,
    CustomerMemoryRepository,
    CustomerRepository,
    EscalationRepository,
    IncidentRepository,
    SubscriptionRepository,
    SupportArticleRepository,
    TicketMessageRepository,
    TicketRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
    WorkspaceRepository,
)
from app.repositories.people import content_hash
from app.schemas.common import ApprovalStatus, RunStatus, TicketStatus
from app.services.seed_service import SEED_TABLES, build_seed_records
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def session():
    from app.models import entities  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        records = build_seed_records()
        for table, repo_class in SEED_TABLES.items():
            await repo_class(db).add_many(records[table])
        await db.commit()
        yield db
    await engine.dispose()


async def _ticket(db: AsyncSession, number: str):
    ticket = await TicketRepository(db).get_by_number(number)
    assert ticket is not None
    return ticket


async def test_cd_1002_and_its_customer_are_readable(session):
    ticket = await _ticket(session, "CD-1002")
    customer = await CustomerRepository(session).get(ticket.customer_id)
    subscription = await SubscriptionRepository(session).get_for_customer(ticket.customer_id)
    assert customer.company == "Brightpath Studio"
    assert (subscription.seats_purchased, subscription.seats_used) == (8, 5)
    assert ticket.status == "new" and ticket.category is None


async def test_counts(session):
    assert await TicketRepository(session).count() == 13
    assert await CustomerRepository(session).count() == 8
    assert await SupportArticleRepository(session).count() == 15


async def test_get_by_number_is_case_insensitive_and_missing_is_none(session):
    assert (await TicketRepository(session).get_by_number(" cd-1001 ")).number == "CD-1001"
    assert await TicketRepository(session).get_by_number("CD-9999") is None


async def test_next_number_follows_the_highest(session):
    assert await TicketRepository(session).next_number() == "CD-1014"


async def test_list_filtered_and_history(session):
    repo = TicketRepository(session)
    assert len(await repo.list_filtered(status="new")) == 13
    assert await repo.list_filtered(status="resolved") == []
    kestrel = (await _ticket(session, "CD-1003")).customer_id
    mine = await repo.list_filtered(customer_id=kestrel)
    assert [t.number for t in mine] == ["CD-1003", "CD-1008"]
    other = await repo.history_for_customer(kestrel, exclude_ticket_id=mine[0].id)
    assert [t.number for t in other] == ["CD-1008"]


async def test_customer_search(session):
    repo = CustomerRepository(session)
    assert [c.company for c in await repo.search("northwind")] == ["Northwind Logistics"]
    assert len(await repo.search("")) == 8
    assert (await repo.get_by_email("PRIYA.NAIR@northwind-logistics.example")) is not None


async def test_workspaces_for_customer(session):
    harbor = (await _ticket(session, "CD-1009")).customer_id
    names = [w.name for w in await WorkspaceRepository(session).list_for_customer(harbor)]
    assert names == ["Active Matters", "Legacy Reports 2021"]


async def test_active_incident_for_sso(session):
    active = await IncidentRepository(session).active("sso")
    assert [i.service for i in active] == ["sso"]
    assert await IncidentRepository(session).active("api") == []


async def test_messages_come_back_in_order(session):
    ticket = await _ticket(session, "CD-1001")
    messages = await TicketMessageRepository(session).list_for_ticket(ticket.id)
    assert len(messages) == 1 and messages[0].sender_type == "customer"


async def test_set_status_stamps_resolved_at(session):
    repo = TicketRepository(session)
    ticket = await _ticket(session, "CD-1010")
    await repo.set_status(ticket, TicketStatus.IN_PROGRESS)
    assert ticket.resolved_at is None
    await repo.set_status(ticket, TicketStatus.RESOLVED)
    assert ticket.resolved_at is not None
    assert (await repo.counts_by_status())["resolved"] == 1


async def test_memory_notes_are_deduplicated_and_capped_at_ten(session):
    repo = CustomerMemoryRepository(session)
    customer = (await _ticket(session, "CD-1002")).customer_id
    first = await repo.add_note(customer, "note", "Prefers email replies")
    again = await repo.add_note(customer, "note", "  prefers EMAIL replies ")
    assert first is not None and again is None
    for n in range(12):
        await repo.add_note(customer, "past_issue", f"issue {n}")
    assert len(await repo.recall(customer)) == 10
    assert content_hash("A  b") == content_hash("a b")


async def test_memory_rejects_unknown_kind(session):
    customer = (await _ticket(session, "CD-1002")).customer_id
    with pytest.raises(IntegrityError):
        await CustomerMemoryRepository(session).add_note(customer, "secret", "x")
    await session.rollback()


async def test_check_constraints_reject_a_bad_category_and_status(session):
    repo = TicketRepository(session)
    customer = (await _ticket(session, "CD-1002")).customer_id
    with pytest.raises(IntegrityError):
        await repo.add(
            number="CD-2000", customer_id=customer, subject="s", body="b", category="made_up"
        )
    await session.rollback()
    with pytest.raises(IntegrityError):
        await repo.add(number="CD-2001", customer_id=customer, subject="s", body="b", status="x")
    await session.rollback()


async def test_foreign_keys_are_enforced_like_postgres(session):
    with pytest.raises(IntegrityError):
        await TicketRepository(session).add(
            number="CD-3000", customer_id="no-such-customer", subject="s", body="b"
        )
    await session.rollback()


async def test_workflow_run_approval_and_escalation_round_trip(session):
    ticket = await _ticket(session, "CD-1002")
    runs = WorkflowRunRepository(session)
    run = await runs.add(ticket_id=ticket.id, thread_id="thread-1", state={"ticket": ticket.number})
    await runs.save_state(run, {"completed_nodes": ["understand_ticket"]}, current_node="understand_ticket")
    assert (await runs.latest_for_ticket(ticket.id)).state["completed_nodes"] == ["understand_ticket"]

    approvals = ApprovalRepository(session)
    approval = await approvals.add(workflow_id=run.id, ticket_id=ticket.id, summary="Refund 3 seats")
    assert [a.id for a in await approvals.pending()] == [approval.id]
    assert (await approvals.pending_for_ticket(ticket.id)).id == approval.id
    await approvals.decide(approval, ApprovalStatus.APPROVED, decided_by=None, note="ok")
    assert await approvals.pending() == []
    assert approval.decided_at is not None

    await runs.set_status(run, RunStatus.COMPLETED)
    assert run.completed_at is not None

    await EscalationRepository(session).add(ticket_id=ticket.id, team="billing", reason="dispute")
    assert len(await EscalationRepository(session).list_for_ticket(ticket.id)) == 1

    await WorkflowEventRepository(session).add(
        workflow_id=run.id, ticket_id=ticket.id, event_type="node_started", node="understand_ticket"
    )
    assert len(await WorkflowEventRepository(session).list_for_ticket(ticket.id)) == 1
