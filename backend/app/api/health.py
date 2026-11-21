"""Health probes, mounted without the ``/api/v1`` prefix.

``/health`` and ``/health/live`` do no I/O (used by container probes).
``/health/ready`` reports configuration only until the stores exist in later
phases; it will gain real db/redis/vector/llm checks then.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import database_configured
"""Unprefixed health probes.

``/health`` and ``/health/live`` do not call readiness or any other dependency.
``/health/ready`` reports configuration only until the data clients exist.
"""

from fastapi import APIRouter, Response, status

from app import SERVICE_NAME, distribution_version
from app.core.config import get_settings
from app.core.readiness import readiness
from app.schemas.health import HealthResponse, LiveResponse, ReadyResponse

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
@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=distribution_version(),
        environment=settings.environment,
    )


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="alive")


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    response_model_exclude_none=True,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(response: Response) -> ReadyResponse:
    body = readiness()
    if body.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body
