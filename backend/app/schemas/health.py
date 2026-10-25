"""Health probe payloads from ``docs/API_CONTRACT.md``."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class LiveResponse(BaseModel):
    status: Literal["alive"]


class ComponentCheck(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class ReadinessChecks(BaseModel):
    database: ComponentCheck
    redis: ComponentCheck
    vector_store: ComponentCheck
    llm: ComponentCheck


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded"]
    checks: ReadinessChecks
