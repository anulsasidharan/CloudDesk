"""FastAPI entrypoint. Middleware order (outermost last): CORS -> RequestId -> RateLimit -> Audit.

Only CORS and RequestId exist in Phase 1; rate limit and audit arrive in Phase 3.
"""CloudDesk ASGI app.

Boot with ``PYTHONPATH=backend`` and ``uvicorn app.main:app``. Middleware is
added innermost first. Rate limiting and audit join this stack in Phase 3,
between the request id and the router.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.middleware.request_id import HEADER_NAME, RequestIdMiddleware


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="CloudDesk Support", version="0.1.0")

    # Added in reverse so the request passes CORS first, then RequestId.
from app import distribution_version
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware


def create_app() -> FastAPI:
    """Build the API. ``setup_logging`` replaces any previous root handlers."""
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="CloudDesk Support", version=distribution_version())
    # Outermost last: CORS → RequestId → (RateLimit → Audit in Phase 3).
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[HEADER_NAME],
    )

    app.include_router(health.router)
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.include_router(health_router)
    return app


app = create_app()
