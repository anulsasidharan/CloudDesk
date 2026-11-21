"""Phase 6: tool policy, registry and tools against a private seeded in-memory database."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from app.core.config import get_settings
from app.core.database import enable_sqlite_foreign_keys
from app.models.base import Base
from app.repositories import (
    EscalationRepository,
    SubscriptionRepository,
    TicketRepository,
    WorkspaceRepository,
)
from app.services.seed_service import (
    SEED_TABLES,
    build_seed_records,
    load_article_files,
    resolve_data_dir,
)
from app.tools import ToolPolicy, ToolRegistry, build_default_registry
from app.tools.base import ToolResult
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from integrations.factory import get_billing, get_workspace_admin, reset_integrations
from integrations.protocols import BillingService, EmailService
from rag.ingest import ingest_articles
from rag.vector_store import InMemoryVectorStore


@pytest.fixture
async def maker(monkeypatch):
    from app.models import entities  # noqa: F401

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

    from app.tools import read_only, write

    monkeypatch.setattr(read_only, "tool_session", private_session)
    monkeypatch.setattr(write, "tool_session", private_session)
    reset_integrations()
    yield factory
    await engine.dispose()


@pytest.fixture
def registry() -> ToolRegistry:
    return build_default_registry()


async def _ticket(maker, number):
    async with maker() as db:
        return await TicketRepository(db).get_by_number(number)


# ---- policy -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "get_customer",
        "get_subscription",
        "get_ticket_history",
        "search_docs",
        "check_service_status",
        "update_ticket",
        "create_escalation",
    ],
)
def test_reads_and_safe_writes_need_no_approval(name):
    assert ToolPolicy.requires_approval(name) is False


@pytest.mark.parametrize("name", ["reset_demo_setting", "create_refund_request"])
def test_money_and_account_tools_need_approval(name):
    assert ToolPolicy.requires_approval(name, {"amount": 10}) is True


def test_unknown_tools_need_approval():
    assert ToolPolicy.requires_approval("drop_database") is True


def test_refund_small_amount_still_gated_by_default_threshold(monkeypatch):
    monkeypatch.setenv("APPROVAL_REQUIRED_FOR_REFUNDS", "false")
    monkeypatch.setenv("MAX_REFUND_WITHOUT_APPROVAL", "0")
    get_settings.cache_clear()
    try:
        assert ToolPolicy.requires_approval("create_refund_request", {"amount": 1}) is True
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_registry_lists_every_tool_with_its_approval_bit(registry):
    specs = {s["name"]: s for s in registry.specs()}
    assert len(specs) == 9
    assert specs["create_refund_request"]["requires_approval"] is True
    assert specs["get_customer"]["requires_approval"] is False
    assert all(s["description"] for s in specs.values())


# ---- the demo checkpoint ----------------------------------------------------------------


async def test_refund_without_approval_writes_nothing(maker, registry):
    ticket = await _ticket(maker, "CD-1002")
    result = await registry.execute(
        "create_refund_request",
        {"customer_id": ticket.customer_id, "amount": 24.0, "reason": "3 unused seats"},
    )
    assert (result.ok, result.status, result.executed) == (False, "approval_required", False)
    assert get_billing().calls == []


async def test_refund_with_approval_runs_through_the_same_path(maker, registry):
    ticket = await _ticket(maker, "CD-1002")
    result = await registry.execute(
        "create_refund_request",
        {"customer_id": ticket.customer_id, "amount": 24.0, "reason": "3 unused seats"},
        approved=True,
    )
    assert result.ok and result.executed and result.data["status"] == "pending_settlement"
    assert len(get_billing().calls) == 1


async def test_reset_setting_needs_approval_then_applies(maker, registry):
    async with maker() as db:
        workspace = (await WorkspaceRepository(db).list_all(limit=1))[0]
        wid = workspace.id
    args = {"workspace_id": wid, "setting": "external_sharing", "value": False}
    blocked = await registry.execute("reset_demo_setting", args)
    assert blocked.status == "approval_required" and get_workspace_admin().calls == []
    done = await registry.execute("reset_demo_setting", args, approved=True)
    assert done.ok
    async with maker() as db:
        assert (await WorkspaceRepository(db).get(wid)).external_sharing is False


async def test_reset_setting_refuses_unlisted_setting(maker, registry):
    result = await registry.execute(
        "reset_demo_setting",
        {"workspace_id": "x", "setting": "owner_email", "value": True},
        approved=True,
    )
    assert result.ok is False and result.status == "error"


# ---- registry behaviour -----------------------------------------------------------------


async def test_unknown_tool_blocked_then_reported_unknown(registry):
    assert (await registry.execute("nope")).status == "approval_required"
    assert (await registry.execute("nope", approved=True)).status == "unknown_tool"


async def test_tool_exception_becomes_failed_result():
    @tool
    async def explode() -> dict:
        """Always fails."""
        raise RuntimeError("boom")

    result = await ToolRegistry([explode]).execute("explode", approved=True)
    assert isinstance(result, ToolResult)
    assert result.ok is False and result.status == "error" and "boom" in result.error


async def test_timeout_uses_tool_timeout_seconds(monkeypatch):
    @tool
    async def slow() -> dict:
        """Sleeps."""
        await asyncio.sleep(5)
        return {}

    monkeypatch.setenv("TOOL_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    try:
        result = await ToolRegistry([slow]).execute("slow", approved=True)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert result.status == "timeout" and result.ok is False


def test_duplicate_registration_is_refused(registry):
    from app.tools.read_only import get_customer

    with pytest.raises(ValueError):
        registry.register(get_customer)


# ---- read-only tools ---------------------------------------------------------------------


async def test_customer_subscription_and_history_tools(maker, registry):
    ticket = await _ticket(maker, "CD-1002")
    customer = await registry.execute("get_customer", {"customer_id": ticket.customer_id})
    assert customer.ok and customer.data["company"] == "Brightpath Studio"
    sub = await registry.execute("get_subscription", {"customer_id": ticket.customer_id})
    assert (sub.data["seats_purchased"], sub.data["seats_used"]) == (8, 5)
    history = await registry.execute(
        "get_ticket_history", {"customer_id": ticket.customer_id, "exclude_ticket_id": ticket.id}
    )
    assert history.ok and all(t["id"] != ticket.id for t in history.data["tickets"])


async def test_missing_customer_is_a_failed_result_not_a_crash(maker, registry):
    result = await registry.execute("get_customer", {"customer_id": "nobody"})
    assert result.ok is False and result.status == "error"


async def test_check_service_status_reports_incident(maker, registry):
    result = await registry.execute("check_service_status", {})
    assert result.ok and isinstance(result.data["operational"], bool)
    assert result.data["operational"] == (not result.data["incidents"])


async def test_search_docs_returns_cited_evidence(monkeypatch, registry):
    store = InMemoryVectorStore()
    await ingest_articles(load_article_files(resolve_data_dir()), store, cache=None)
    monkeypatch.setattr("rag.retriever.get_vector_store", lambda: store)
    result = await registry.execute(
        "search_docs", {"query": "locked out after MFA attempts recovery"}
    )
    assert result.ok and result.data["evidence"]
    assert result.data["evidence"][0]["source"].startswith("kb://")


# ---- write tools --------------------------------------------------------------------------


async def test_update_ticket_changes_status_and_validates_values(maker, registry):
    ticket = await _ticket(maker, "CD-1010")
    ok = await registry.execute(
        "update_ticket", {"ticket_id": ticket.id, "status": "in_progress", "severity": "low"}
    )
    assert ok.ok and ok.data["status"] == "in_progress"
    bad = await registry.execute("update_ticket", {"ticket_id": ticket.id, "category": "magic"})
    assert bad.ok is False


async def test_create_escalation_writes_row_and_notifies_team(maker, registry):
    ticket = await _ticket(maker, "CD-1005")
    result = await registry.execute(
        "create_escalation",
        {"ticket_id": ticket.id, "team": "security", "reason": "possible breach"},
    )
    assert result.ok and result.data["team"] == "security"
    async with maker() as db:
        rows = await EscalationRepository(db).list_for_ticket(ticket.id)
    assert [r.team for r in rows] == ["security"]


# ---- integrations -------------------------------------------------------------------------


async def test_mock_integrations_satisfy_protocols_and_record_calls(maker):
    from integrations.factory import get_email

    assert isinstance(get_billing(), BillingService) and isinstance(get_email(), EmailService)
    sent = await get_email().send_email(to="a@b.c", subject="s", body="b")
    assert sent["status"] == "not_sent_mock" and sent["message_id"] == "msg_mock_0001"


def test_unused_imports_guard():
    assert SubscriptionRepository is not None
