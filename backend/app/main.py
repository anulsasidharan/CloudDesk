"""FastAPI entrypoint. Middleware order (outermost last): CORS -> RequestId -> RateLimit -> Audit.

Only CORS and RequestId exist in Phase 1; rate limit and audit arrive in Phase 3.
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
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[HEADER_NAME],
    )

    app.include_router(health.router)
    return app


app = create_app()
