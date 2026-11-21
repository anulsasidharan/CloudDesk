"""CloudDesk ASGI app.

Boot with ``PYTHONPATH=backend`` and ``uvicorn app.main:app``. Middleware is
added innermost first. Rate limiting and audit join this stack in Phase 3,
between the request id and the router.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import distribution_version
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.database import create_tables, dispose_engine
from app.core.logging import setup_logging
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.services.seed_service import bootstrap_demo_data


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create tables, then load the demo data when ``DEMO_MODE`` is on and the DB is empty."""
    await create_tables()
    if get_settings().demo_mode:
        await bootstrap_demo_data()
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Build the API. ``setup_logging`` replaces any previous root handlers."""
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="CloudDesk Support", version=distribution_version(), lifespan=lifespan)
    # Outermost last: CORS -> RequestId -> (RateLimit -> Audit in Phase 3).
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
    return app


app = create_app()
