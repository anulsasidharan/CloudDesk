"""F14 offline settings, and JSON logs that always carry request and workflow ids."""

import io
import json
import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter, log_context, setup_logging

_ENV_KEYS = (
    "DEMO_MODE",
    "ENVIRONMENT",
    "CORS_ORIGINS",
    "JWT_SECRET",
    "SUPABASE_JWT_SECRET",
    "DATABASE_URL",
    "CHECKPOINT_DB_PATH",
    "REDIS_URL",
    "USE_FAKE_REDIS",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "VECTOR_STORE",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "APPROVAL_REQUIRED_FOR_REFUNDS",
    "MAX_REFUND_WITHOUT_APPROVAL",
    "TOOL_TIMEOUT_SECONDS",
    "RATE_LIMIT_PER_MINUTE",
    "SAMPLE_DATA_DIR",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT",
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
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


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _isolated_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_settings_fields_match_env_contract():
    assert {name.upper() for name in Settings.model_fields} == set(_ENV_KEYS)


def test_f14_offline_defaults_need_no_api_key(monkeypatch: pytest.MonkeyPatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    settings = _isolated_settings()
    assert settings.demo_mode is True
    assert settings.llm_provider == "fake"
    assert settings.embedding_provider == "fake"
    assert settings.llm_api_key.get_secret_value() == ""
    assert settings.vector_store == "memory"
    assert settings.embedding_dimensions == 384
    assert settings.qdrant_collection == "clouddesk_knowledge"
    assert settings.approval_required_for_refunds is True
    assert settings.max_refund_without_approval == 0
    assert settings.rate_limit_per_minute == 120
    assert settings.langchain_tracing_v2 is False
    assert settings.langchain_project == "clouddesk-support"
    assert settings.database_url == "sqlite+aiosqlite:///./data/support.db"
    assert settings.checkpoint_db_path == "./data/checkpoints.db"
    assert settings.uses_fake_redis is True
    assert settings.cors_origin_list == ["http://localhost:3000"]
    assert settings.effective_jwt_secret == ""


def test_settings_read_demo_mode_and_llm_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    settings = get_settings()
    assert settings.demo_mode is False
    assert settings.llm_provider == "openai"
    assert get_settings() is settings


def test_get_settings_keeps_cached_values_until_cleared(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    get_settings.cache_clear()
    assert get_settings().llm_provider == "fake"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert get_settings().llm_provider == "fake"
    get_settings.cache_clear()
    assert get_settings().llm_provider == "anthropic"


def test_effective_jwt_secret_prefers_supabase_secret():
    local_only = _isolated_settings(jwt_secret="local-secret")
    assert local_only.effective_jwt_secret == "local-secret"
    both = _isolated_settings(jwt_secret="local-secret", supabase_jwt_secret="supabase-secret")
    assert both.effective_jwt_secret == "supabase-secret"


def test_uses_fake_redis_when_forced_or_url_missing():
    assert _isolated_settings(redis_url="redis://redis:6379/0").uses_fake_redis is False
    forced = _isolated_settings(redis_url="redis://redis:6379/0", use_fake_redis=True)
    assert forced.uses_fake_redis is True


def test_cors_origins_split_on_commas():
    settings = _isolated_settings(cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert settings.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_vector_store_rejects_unknown_backend():
    with pytest.raises(ValidationError):
        _isolated_settings(vector_store="pinecone")


def test_repr_and_dump_hide_secrets_and_url_passwords():
    settings = _isolated_settings(
        jwt_secret="jwt-secret-value",
        llm_api_key="sk-live-123",
        database_url="postgresql+asyncpg://user:s3cret-pass@localhost:5432/support",
        redis_url="redis://:redis-pass@localhost:6379/0",
    )
    rendered = f"{settings!r} {settings!s}"
    assert "jwt-secret-value" not in rendered
    assert "sk-live-123" not in rendered
    assert "s3cret-pass" not in rendered
    assert "redis-pass" not in rendered
    dumped = settings.model_dump()
    assert dumped["jwt_secret"] == "**********"
    assert dumped["llm_api_key"] == "**********"
    assert dumped["database_url"] == "postgresql+asyncpg://***@localhost:5432/support"
    assert dumped["redis_url"] == "redis://***@localhost:6379/0"
    assert settings.database_url == "postgresql+asyncpg://user:s3cret-pass@localhost:5432/support"
    assert settings.jwt_secret.get_secret_value() == "jwt-secret-value"


def test_json_formatter_includes_ids_and_ignores_extra_fields():
    formatter = JsonFormatter()
    record = _record("hello\nworld", api_key="sk-live-should-not-appear", request_id="req-extra")
    with log_context(request_id="req-context", workflow_id="wf-1"):
        line = formatter.format(record)
    assert "\n" not in line
    assert "sk-live-should-not-appear" not in line
    payload = json.loads(line)
    assert payload["message"] == "hello\nworld"
    assert payload["request_id"] == "req-extra"
    assert payload["workflow_id"] == "wf-1"
    assert set(payload) == {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "workflow_id",
    }


def test_log_context_restores_outer_ids():
    formatter = JsonFormatter()
    with log_context(request_id="req"):
        with log_context(workflow_id="wf"):
            inner = json.loads(formatter.format(_record("inner")))
        outer = json.loads(formatter.format(_record("outer")))
    outside = json.loads(formatter.format(_record("outside")))
    assert inner["request_id"] == "req"
    assert inner["workflow_id"] == "wf"
    assert outer["request_id"] == "req"
    assert outer["workflow_id"] is None
    assert outside["request_id"] is None
    assert outside["workflow_id"] is None


def test_setup_logging_writes_one_json_line(log_buffer: io.StringIO):
    with log_context(request_id="req-42", workflow_id="wf-7"):
        logging.getLogger("clouddesk").warning("ticket queued")
    logging.getLogger("clouddesk").debug("hidden")
    lines = [line for line in log_buffer.getvalue().splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "clouddesk"
    assert payload["message"] == "ticket queued"
    assert payload["request_id"] == "req-42"
    assert payload["workflow_id"] == "wf-7"


def test_setup_logging_includes_exception_on_one_line(log_buffer: io.StringIO):
    logger = logging.getLogger("clouddesk")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.exception("failed")
    line = log_buffer.getvalue().splitlines()[-1]
    assert "\n" not in line
    payload = json.loads(line)
    assert "RuntimeError: boom" in payload["exception"]
    assert payload["request_id"] is None
    assert payload["workflow_id"] is None


def test_setup_logging_replaces_previous_handlers(log_buffer: io.StringIO):
    setup_logging(stream=log_buffer)
    root = logging.getLogger()
    assert len(root.handlers) == 1
