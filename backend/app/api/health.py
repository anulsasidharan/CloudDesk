"""Health probes, mounted without the ``/api/v1`` prefix.

``/health`` and ``/health/live`` do no I/O (used by container probes).
``/health/ready`` reports configuration only until the stores exist in later
phases; it will gain real db/redis/vector/llm checks then.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import database_configured

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict[str, object]:
    settings = get_settings()
    checks = {
        "db": "configured" if database_configured() else "missing",
        "redis": "fake" if settings.uses_fake_redis else "configured",
        "vector_store": settings.vector_store,
        "llm": settings.llm_provider,
    }
    ok = checks["db"] != "missing"
    return {"status": "ok" if ok else "degraded", "checks": checks}
