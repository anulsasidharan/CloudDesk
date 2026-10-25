"""N3: health probes stay free of dependency I/O, and every response carries X-Request-ID."""

import io
import json
import logging
import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app import SERVICE_NAME, distribution_version
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.core.readiness import readiness
from app.main import create_app
from app.middleware.request_id import resolve_request_id

_OFFLINE = {
    "ENVIRONMENT": "development",
    "CORS_ORIGINS": "http://localhost:3000",
    "DATABASE_URL": "sqlite+aiosqlite:///./data/support.db",
    "REDIS_URL": "",
    "USE_FAKE_REDIS": "false",
    "VECTOR_STORE": "memory",
    "LLM_PROVIDER": "fake",
    "LLM_API_KEY": "",
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch):
    for key, value in _OFFLINE.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.fixture
def log_buffer():
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    buffer = io.StringIO()
    setup_logging(stream=buffer)
    yield buffer
    root.handlers.clear()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def _client() -> TestClient:
    return TestClient(create_app())


def _log_named(buffer: io.StringIO, message: str) -> dict[str, object]:
    matches = [
        json.loads(line)
        for line in buffer.getvalue().splitlines()
        if line and json.loads(line)["message"] == message
    ]
    assert len(matches) == 1
    return matches[0]


def test_resolve_request_id_echoes_safe_values_and_replaces_the_rest():
    assert resolve_request_id("req-health-1") == "req-health-1"
    assert resolve_request_id("abc.def:ghi_01") == "abc.def:ghi_01"
    generated = resolve_request_id(None)
    assert uuid.UUID(generated).version == 4
    assert resolve_request_id("bad id") != "bad id"
    assert resolve_request_id("line\nbreak") != "line\nbreak"
    assert resolve_request_id("") != ""
    assert resolve_request_id("x" * 129) != "x" * 129


def test_health_and_live_skip_readiness_and_report_process_identity(offline_env, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("readiness probe ran")

    monkeypatch.setattr("app.api.health.readiness", explode)
    with _client() as client:
        health = client.get("/health")
        live = client.get("/health/live")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": distribution_version(),
        "environment": "development",
    }
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert "checks" not in health.json()
    assert "checks" not in live.json()


def test_ready_is_ready_for_offline_backends(offline_env):
    with _client() as client:
        response = client.get("/health/ready")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ready"
    assert set(body["checks"]) == {"database", "redis", "vector_store", "llm"}
    assert all(check == {"status": "ok"} for check in body["checks"].values())


def test_ready_is_degraded_without_leaking_secrets():
    secret_url = "postgresql+asyncpg://user:s3cret-pass@localhost:5432/support"
    secret_redis = "redis://:redis-pass@localhost:6379/0"
    secret_key = "sk-live-health-probe"
    settings = Settings(
        _env_file=None,
        database_url=secret_url,
        redis_url=secret_redis,
        use_fake_redis=False,
        vector_store="qdrant",
        llm_provider="openai",
        llm_api_key=secret_key,
    )
    body = readiness(settings).model_dump()
    encoded = json.dumps(body)
    assert body["status"] == "degraded"
    assert {name: check["status"] for name, check in body["checks"].items()} == {
        "database": "error",
        "redis": "error",
        "vector_store": "error",
        "llm": "error",
    }
    assert "s3cret-pass" not in encoded
    assert "redis-pass" not in encoded
    assert secret_key not in encoded
    assert "localhost" not in encoded


def test_ready_http_status_is_503_when_degraded(offline_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    with _client() as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["llm"]["status"] == "error"
    assert response.json()["checks"]["database"]["status"] == "ok"


def test_every_response_carries_request_id(offline_env):
    with _client() as client:
        echoed = client.get("/health/live", headers={"X-Request-ID": "req-health-1"})
        generated = client.get("/health")
        replaced = client.get("/health/live", headers={"X-Request-ID": "bad id"})
        missing = client.get("/no-such-route", headers={"X-Request-ID": "missing-1"})
        docs = client.get("/openapi.json")

    assert echoed.headers["x-request-id"] == "req-health-1"
    parsed = uuid.UUID(generated.headers["x-request-id"])
    assert parsed.version == 4
    assert replaced.headers["x-request-id"] != "bad id"
    assert uuid.UUID(replaced.headers["x-request-id"]).version == 4
    assert missing.status_code == 404
    assert missing.headers["x-request-id"] == "missing-1"
    assert missing.json()["detail"] == "Not Found"
    assert docs.status_code == 200
    assert docs.headers["x-request-id"]


def test_request_id_is_on_the_log_line_and_cleared_afterward(offline_env, log_buffer: io.StringIO):
    app = create_app()
    setup_logging(stream=log_buffer)

    @app.get("/__log")
    def emit_log() -> dict[str, bool]:
        logging.getLogger("clouddesk.test").info("probe")
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/__log", headers={"X-Request-ID": "req-log-9"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-log-9"
    payload = _log_named(log_buffer, "probe")
    assert payload["request_id"] == "req-log-9"
    assert payload["workflow_id"] is None


def test_unhandled_error_hides_the_exception_and_keeps_the_request_id(offline_env, log_buffer: io.StringIO):
    app = create_app()
    setup_logging(stream=log_buffer)

    @app.get("/__boom")
    def boom() -> None:
        raise RuntimeError("boom-secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "boom-secret" not in response.text
    assert response.headers["x-request-id"] == "req-500"
    payload = _log_named(log_buffer, "unhandled error")
    assert payload["request_id"] == "req-500"
    assert "boom-secret" in payload["exception"]
    assert "boom-secret" not in response.headers.get("x-request-id", "")


def test_cors_exposes_request_id_to_the_console_origin(offline_env):
    with _client() as client:
        response = client.get("/health/live", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"]


def test_request_state_carries_the_id(offline_env):
    app = create_app()

    @app.get("/__state")
    def show(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    with TestClient(app) as client:
        response = client.get("/__state", headers={"X-Request-ID": "state-7"})
    assert response.json() == {"request_id": "state-7"}
