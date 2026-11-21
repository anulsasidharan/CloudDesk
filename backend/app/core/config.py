"""Process settings loaded from the environment and an optional ``.env`` file.

``get_settings()`` is cached for the life of the process. Restart the server
after a ``.env`` change. Secret fields and URL passwords are omitted from
``repr`` and redacted in ``model_dump()``. Read ``database_url`` and
``redis_url`` from the object when opening a connection.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_serializer, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> backend -> repository root
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

_SECRET_FIELDS = (
    "jwt_secret",
    "supabase_jwt_secret",
    "llm_api_key",
    "qdrant_api_key",
    "langchain_api_key",
)


def _redact_url(url: str) -> str:
    """Hide userinfo in a URL. SQLite paths and empty values stay unchanged."""
    if "://" not in url or "@" not in url:
        return url
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, f"***@{host}", parts.path, parts.query, parts.fragment))


class Settings(BaseSettings):
    """Environment contract from ``CLAUDE.md`` section 10.1."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    demo_mode: bool = True
    environment: str = "development"
    cors_origins: str = "http://localhost:3000"

    jwt_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    supabase_jwt_secret: SecretStr = Field(default=SecretStr(""), repr=False)

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/support.db",
        repr=False,
    )
    checkpoint_db_path: str = "./data/checkpoints.db"

    redis_url: str = Field(default="", repr=False)
    use_fake_redis: bool = False

    llm_provider: str = "fake"
    llm_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    llm_model: str = ""

    embedding_provider: str = "fake"
    embedding_model: str = ""
    embedding_dimensions: int = 384

    vector_store: Literal["memory", "qdrant"] = "memory"
    qdrant_url: str = ""
    qdrant_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    qdrant_collection: str = "clouddesk_knowledge"

    approval_required_for_refunds: bool = True
    max_refund_without_approval: float = 0
    tool_timeout_seconds: float = 30

    rate_limit_per_minute: int = 120
    sample_data_dir: str = "sample_data"

    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    langchain_project: str = "clouddesk-support"

    @field_validator("llm_provider", "embedding_provider", "vector_store", "environment", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_serializer(*_SECRET_FIELDS)
    def _serialize_secret(self, value: SecretStr) -> str:
        if value.get_secret_value():
            return "**********"
        return ""

    @field_serializer("database_url", "redis_url")
    def _serialize_url(self, value: str) -> str:
        return _redact_url(value)

    @property
    def effective_jwt_secret(self) -> str:
        """Supabase JWT secret when set, otherwise ``JWT_SECRET``."""
        supabase = self.supabase_jwt_secret.get_secret_value()
        if supabase:
            return supabase
        return self.jwt_secret.get_secret_value()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def uses_fake_redis(self) -> bool:
        """Fakeredis when ``USE_FAKE_REDIS`` is set or ``REDIS_URL`` is empty."""
        return self.use_fake_redis or self.redis_url.strip() == ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings. Cached until restart; tests call ``cache_clear()``."""
    return Settings()
