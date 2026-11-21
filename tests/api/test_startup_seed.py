"""Phase 2: startup on an empty SQLite file loads the demo data once and never duplicates it."""

import sqlite3

import pytest
from app.core.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


def _count(db_path, table: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"select count(*) from {table}").fetchone()[0]


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "support.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_startup_loads_13_tickets_and_8_customers_then_stays_idempotent(fresh_db):
    with TestClient(create_app()):
        pass
    assert _count(fresh_db, "tickets") == 13
    assert _count(fresh_db, "customers") == 8
    assert _count(fresh_db, "support_articles") == 15

    with TestClient(create_app()):
        pass
    assert _count(fresh_db, "tickets") == 13
    assert _count(fresh_db, "customers") == 8
    assert _count(fresh_db, "profiles") == 3


def test_startup_outside_demo_mode_creates_tables_but_loads_nothing(fresh_db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    with TestClient(create_app()):
        pass
    assert _count(fresh_db, "tickets") == 0
    assert _count(fresh_db, "customers") == 0


def test_a_populated_database_is_left_alone(fresh_db):
    with TestClient(create_app()):
        pass
    with sqlite3.connect(fresh_db) as connection:
        connection.execute("delete from ticket_messages where ticket_id in "
                           "(select id from tickets where number = 'CD-1013')")
        connection.execute("delete from tickets where number = 'CD-1013'")
    with TestClient(create_app()):
        pass
    assert _count(fresh_db, "tickets") == 12  # no reload over existing data


def test_readiness_still_ok_with_the_real_database(fresh_db):
    with TestClient(create_app()) as client:
        assert client.get("/health/ready").status_code == 200
