"""N3: read or create ``X-Request-ID`` and echo it on every response.

Pure ASGI (not ``BaseHTTPMiddleware``) so the context variable set here is
visible to route handlers and background tasks.
"""

import re
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_context

HEADER_NAME = "X-Request-ID"
_HEADER_BYTES = HEADER_NAME.lower().encode("latin-1")
# Reject anything that could forge log lines or headers; a fresh id is used instead.
_VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


def _resolve_request_id(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name == _HEADER_BYTES:
            candidate = value.decode("latin-1")
            if _VALID_ID.match(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        with log_context(request_id=request_id):
            await self.app(scope, receive, send_with_id)
