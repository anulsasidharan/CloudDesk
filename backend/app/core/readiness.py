"""Configuration checks for ``/health/ready``.

These probes do not open a database, Redis, Qdrant, or an LLM connection.
Offline backends (SQLite, fakeredis, the in-memory vector store, and the fake
LLM) are treated as ready. A remote backend stays ``error`` until its client
exists, and the detail never includes a URL, password, or API key.
"""

from app.core.config import Settings, get_settings
from app.schemas.health import ComponentCheck, ReadinessChecks, ReadyResponse


def readiness(settings: Settings | None = None) -> ReadyResponse:
    """Return ready when every configured backend can run without a remote service."""
    current = settings if settings is not None else get_settings()
    checks = ReadinessChecks(
        database=_database(current),
        redis=_redis(current),
        vector_store=_vector_store(current),
        llm=_llm(current),
    )
    ok = all(
        check.status == "ok"
        for check in (checks.database, checks.redis, checks.vector_store, checks.llm)
    )
    return ReadyResponse(status="ready" if ok else "degraded", checks=checks)


def _database(settings: Settings) -> ComponentCheck:
    url = settings.database_url.strip()
    if not url:
        return ComponentCheck(status="error", detail="database url is empty")
    scheme = url.split(":", 1)[0].lower()
    if scheme.startswith("sqlite"):
        return ComponentCheck(status="ok")
    return ComponentCheck(status="error", detail="database connectivity is not probed yet")


def _redis(settings: Settings) -> ComponentCheck:
    if settings.uses_fake_redis:
        return ComponentCheck(status="ok")
    return ComponentCheck(status="error", detail="redis connectivity is not probed yet")


def _vector_store(settings: Settings) -> ComponentCheck:
    if settings.vector_store == "memory":
        return ComponentCheck(status="ok")
    return ComponentCheck(status="error", detail="vector store connectivity is not probed yet")


def _llm(settings: Settings) -> ComponentCheck:
    if settings.llm_provider == "fake":
        return ComponentCheck(status="ok")
    return ComponentCheck(status="error", detail="llm connectivity is not probed yet")
