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
    "JWT_SECRET": "test-secret-not-for-production",
    "SUPABASE_JWT_SECRET": "",
    "LLM_API_KEY": "",
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
