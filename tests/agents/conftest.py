"""Fixtures for the specialist tests: a private seeded database, a private index, real tools."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from app.core import database
from app.core.database import enable_sqlite_foreign_keys
from app.models.base import Base
from app.repositories import CustomerRepository, TicketRepository
from app.services.seed_service import (
    SEED_TABLES,
    build_seed_records,
    load_article_files,
    resolve_data_dir,
)
from app.tools import build_default_registry
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agents.specialists import (
    CustomerAgent,
    EscalationAgent,
    KnowledgeAgent,
    ResolutionAgent,
    SupervisorAgent,
    TroubleshootingAgent,
)
from integrations.factory import reset_integrations
from rag.ingest import ingest_articles
from rag.vector_store import InMemoryVectorStore


@pytest.fixture
async def maker(monkeypatch):
    from app.models import entities  # noqa: F401
    from app.tools import read_only, write

    from rag import retriever

    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        records = build_seed_records()
        for table, repo_class in SEED_TABLES.items():
            await repo_class(db).add_many(records[table])
        await db.commit()

    @asynccontextmanager
    async def private_session():
        async with factory() as session:
            yield session
            await session.commit()

    store = InMemoryVectorStore()
    await ingest_articles(load_article_files(resolve_data_dir()), store, cache=None)

    monkeypatch.setattr(read_only, "tool_session", private_session)
    monkeypatch.setattr(write, "tool_session", private_session)
    monkeypatch.setattr(database, "session_scope", private_session)
    monkeypatch.setattr(retriever, "get_vector_store", lambda: store)
    monkeypatch.setattr(retriever, "_safe_default_cache", lambda: None)
    reset_integrations()
    yield factory
    await engine.dispose()


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def ticket(maker):
    """``await ticket("CD-1002")`` -> the ticket row's fields plus the customer."""

    async def load(number: str):
        async with maker() as db:
            row = await TicketRepository(db).get_by_number(number)
            customer = await CustomerRepository(db).get(row.customer_id)
            others = [c for c in await CustomerRepository(db).list_all() if c.id != customer.id]
        return SimpleNamespace(
            id=row.id,
            number=row.number,
            subject=row.subject,
            body=row.body,
            customer_id=row.customer_id,
            plan=customer.plan,
            others=[c.name for c in others] + [c.company for c in others],
        )

    return load


@pytest.fixture
def pipeline(ticket, registry):
    """Run all specialists on one ticket, in graph order, and return every output."""

    async def run(number: str):
        t = await ticket(number)
        cls = (await SupervisorAgent().understand(t.subject, t.body)).output
        sev = (await SupervisorAgent().assess_severity(t.subject, t.body, cls.category, t.plan)).output
        ctx = (await CustomerAgent().run(t.customer_id, t.id, registry)).output
        know = (await KnowledgeAgent().run(t.subject, t.body, cls.category.value, registry)).output
        diag = (
            await TroubleshootingAgent().run(
                t.subject, t.body, cls.category, ctx, know.evidence, know.previous_cases, registry
            )
        ).output
        plan = (
            await ResolutionAgent().run(
                ticket_id=t.id,
                subject=t.subject,
                body=t.body,
                classification=cls,
                severity=sev.severity,
                context=ctx,
                diagnosis=diag,
                evidence=know.evidence,
                other_customer_markers=t.others,
            )
        ).output
        esc = (await EscalationAgent().run(t.subject, t.body, t.plan, sev.severity)).output
        return SimpleNamespace(
            t=t, cls=cls, sev=sev, ctx=ctx, know=know, diag=diag, plan=plan, esc=esc
        )

    return run
