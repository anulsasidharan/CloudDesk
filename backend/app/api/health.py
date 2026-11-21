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
