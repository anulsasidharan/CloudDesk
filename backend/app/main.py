"""CloudDesk ASGI app.

Boot with ``PYTHONPATH=backend`` and ``uvicorn app.main:app``. Middleware is
added innermost first. Request path: CORS, request id, rate limit, audit, router.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.checkpointer import close_checkpointer
from app import distribution_version
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.tickets import router as tickets_router
from app.core.config import get_settings
from app.core.database import create_tables, dispose_engine
from app.core.logging import setup_logging
from app.core.redis import close_redis
from app.middleware.audit import AuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.services.knowledge_service import ensure_indexed
from app.services.seed_service import bootstrap_demo_data


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create tables, then load the demo data when ``DEMO_MODE`` is on and the DB is empty."""
    await create_tables()
    if get_settings().demo_mode:
        await bootstrap_demo_data()
    try:
        await ensure_indexed()
    except Exception:  # search retries on first use; a bad index must not stop the API booting
        logging.getLogger("app.knowledge").warning("knowledge indexing failed", exc_info=True)
    try:
        yield
    finally:
        await close_checkpointer()
        await dispose_engine()
        await close_redis()


def create_app() -> FastAPI:
    """Build the API. ``setup_logging`` replaces any previous root handlers."""
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="CloudDesk Support", version=distribution_version(), lifespan=lifespan)
    # add_middleware wraps: the LAST one added is outermost.
    # Request path: CORS -> RequestId -> RateLimit -> Audit -> router.
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(tickets_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(customers_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    return app


app = create_app()
