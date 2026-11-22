"""Phase 8: short-term (fakeredis), long-term (SQLite) and the recall/record service."""

import json

import fakeredis
import pytest
from app.core.database import enable_sqlite_foreign_keys
from app.models.base import Base
from app.repositories import CustomerRepository
from app.services.seed_service import SEED_TABLES, build_seed_records
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from memory.long_term import LongTermMemory
from memory.memory_service import MemoryService
from memory.short_term import (
    RETRIEVAL_CACHE_TTL_SECONDS,
    SHORT_TERM_TTL_SECONDS,
    ShortTermMemory,
    retrieval_cache_key,
)

CARD = "4111 1111 1111 1111"
KEY = "sk-abcdefghijklmnop1234567890"


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


@pytest.fixture
async def customer_ids(session: AsyncSession) -> list[str]:
    return [c.id for c in await CustomerRepository(session).list_all()]


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


# ---------------------------------------------------------------- short-term
async def test_conversation_round_trip_and_24h_ttl(redis):
    stm = ShortTermMemory(redis)
    assert await stm.append_message("t1", "customer", "hello")
    await stm.append_message("t1", "agent", "hi")
    assert [m["role"] for m in await stm.get_conversation("t1")] == ["customer", "agent"]
    assert SHORT_TERM_TTL_SECONDS == 86400
    assert 0 < await redis.ttl("conv:t1") <= SHORT_TERM_TTL_SECONDS


async def test_conversation_scrubs_secrets_and_caps_length(redis):
    stm = ShortTermMemory(redis)
    await stm.append_message("t1", "customer", f"my key is {KEY}")
    assert KEY not in (await stm.get_conversation("t1"))[0]["content"]
    for n in range(60):
        await stm.append_message("t2", "customer", f"m{n}")
    convo = await stm.get_conversation("t2")
    assert len(convo) == 50 and convo[-1]["content"] == "m59"


async def test_workflow_state_round_trip_ttl_and_clear(redis):
    stm = ShortTermMemory(redis)
    await stm.save_workflow_state("t1", {"current_node": "knowledge_retrieval"})
    assert (await stm.get_workflow_state("t1"))["current_node"] == "knowledge_retrieval"
    assert 0 < await redis.ttl("wfstate:t1") <= SHORT_TERM_TTL_SECONDS
    await stm.clear("t1")
    assert await stm.get_workflow_state("t1") is None
    assert await stm.get_workflow_state("never") is None


async def test_short_term_fails_soft_when_redis_is_down():
    class Broken:
        def __getattr__(self, name):
            async def boom(*args, **kwargs):
                raise ConnectionError("down")

            return boom

    stm = ShortTermMemory(Broken())
    assert await stm.append_message("t", "customer", "x") is False
    assert await stm.get_conversation("t") == []
    assert await stm.get_workflow_state("t") is None


def test_retrieval_cache_contract():
    assert retrieval_cache_key("hybrid", "billing", 3, "refund") == "rag:hybrid:billing:3:refund"
    assert RETRIEVAL_CACHE_TTL_SECONDS == 300


# ---------------------------------------------------------------- long-term
async def test_remember_scrubs_and_dedupes(session, customer_ids):
    ltm = LongTermMemory(session)
    cid = customer_ids[0]
    text = f"Paid with {CARD}, password: hunter22x"
    note = await ltm.remember(cid, "note", text)
    assert note and "4111" not in note.content and "hunter22x" not in note.content
    assert "[REDACTED:card_number]" in note.content
    assert await ltm.remember(cid, "note", text) is None
    assert await ltm.remember(cid, "note", "   ") is None
    with pytest.raises(ValueError):
        await ltm.remember(cid, "secret", "x")


async def test_recall_caps_at_ten_and_isolates_customers(session, customer_ids):
    ltm = LongTermMemory(session)
    a, b = customer_ids[:2]
    for n in range(15):
        await ltm.remember(a, "past_issue", f"issue {n}")
    await ltm.remember(b, "note", "only b")
    assert len(await ltm.recall(a)) == 10
    assert [n.content for n in await ltm.recall(b)] == ["only b"]


# ---------------------------------------------------------------- service
async def test_record_resolution_writes_five_notes_with_three_steps(session, customer_ids):
    svc = MemoryService(session)
    cid = customer_ids[0]
    ticket_id = (await _any_ticket_id(session))
    result = await svc.record_resolution(
        cid,
        ticket_id,
        issue_summary="Charged for 8 seats, uses 5",
        troubleshooting_steps=["Check seats", "Compare invoice", "Confirm usage", "Fourth step"],
        resolution_summary="Refund for 3 seats requested",
    )
    assert (result.written, result.skipped_duplicates) == (5, 0)
    notes = await svc.recall_customer(cid)
    kinds = sorted(n.kind for n in notes)
    assert kinds == ["note", "past_issue", "troubleshooting", "troubleshooting", "troubleshooting"]
    assert all("Fourth" not in n.content for n in notes)
    assert all(n.source_ticket_id == ticket_id for n in notes)


async def test_recording_twice_does_not_duplicate(session, customer_ids):
    """Demo checkpoint: running CD-1002 twice does not duplicate the resolution note."""
    svc = MemoryService(session)
    cid = customer_ids[0]
    ticket_id = await _any_ticket_id(session)
    kwargs = {
        "issue_summary": "Seat overcharge",
        "troubleshooting_steps": ["a", "b", "c"],
        "resolution_summary": "Refund requested",
    }
    await svc.record_resolution(cid, ticket_id, **kwargs)
    second = await svc.record_resolution(cid, ticket_id, **kwargs)
    assert (second.written, second.skipped_duplicates) == (0, 5)
    assert len(await svc.recall_customer(cid)) == 5


async def test_no_secrets_reach_the_table(session, customer_ids):
    from app.models.entities import CustomerMemory

    svc = MemoryService(session)
    await svc.record_resolution(
        customer_ids[0],
        await _any_ticket_id(session),
        issue_summary=f"Key {KEY} leaked",
        troubleshooting_steps=["Rotate; password: Sup3rSecret!"],
        resolution_summary=f"Card {CARD} on file",
    )
    blob = json.dumps(
        [r.content for r in (await session.execute(select(CustomerMemory))).scalars()]
    )
    for leaked in ("sk-abcdefgh", "Sup3rSecret", "4111 1111"):
        assert leaked not in blob


async def _any_ticket_id(session: AsyncSession) -> str:
    from app.repositories import TicketRepository

    return (await TicketRepository(session).list_all())[0].id
