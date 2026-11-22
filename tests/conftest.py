"""Offline harness. Env vars are set BEFORE the app is imported (CLAUDE.md section 13)."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="clouddesk-tests-"))

_OFFLINE_ENV = {
    "DEMO_MODE": "true",
    "LLM_PROVIDER": "fake",
    "EMBEDDING_PROVIDER": "fake",
    "VECTOR_STORE": "memory",
    "USE_FAKE_REDIS": "true",
    "REDIS_URL": "",
    "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'support.db').as_posix()}",
    "CHECKPOINT_DB_PATH": ":memory:",
    "JWT_SECRET": "test-secret-not-for-production-use-only-32b",
    "SUPABASE_JWT_SECRET": "",
    "LLM_API_KEY": "",
    "RATE_LIMIT_PER_MINUTE": "100000",  # rate-limit tests build their own limiter
}
os.environ.update(_OFFLINE_ENV)

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client() -> TestClient:
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _headers_for(client: TestClient, role: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/demo-login", json={"role": role})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def agent_headers(client: TestClient) -> dict[str, str]:
    return _headers_for(client, "agent")


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict[str, str]:
    return _headers_for(client, "admin")


@pytest.fixture(scope="session")
def viewer_headers(client: TestClient) -> dict[str, str]:
    return _headers_for(client, "viewer")
