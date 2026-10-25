"""Assign ``X-Request-ID`` and bind it for JSON logs. Requirement N3."""

import logging
import re
import uuid
from collections.abc import MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_context

REQUEST_ID_HEADER = "X-Request-ID"
INTERNAL_ERROR_DETAIL = "Internal Server Error"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_logger = logging.getLogger("app.middleware.request_id")


def resolve_request_id(raw: str | None) -> str:
    """Echo a safe caller id, or assign a new UUID."""
    if raw and _REQUEST_ID_RE.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


def _incoming_request_id(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"x-request-id":
            return value.decode("latin-1").strip()
    return None


def _store_request_id(scope: Scope, request_id: str) -> None:
    state: MutableMapping[str, Any] | Any = scope.setdefault("state", {})
    if isinstance(state, dict):
        state["request_id"] = request_id
        return
    state.request_id = request_id


class RequestIdMiddleware:
    """Pure ASGI middleware so the request id stays on the same task as the route."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(_incoming_request_id(scope))
        _store_request_id(scope, request_id)
        started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        with log_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                if started:
                    raise
                _logger.exception("unhandled error")
                body = b'{"detail":"Internal Server Error"}'
                await send_with_request_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                        ],
                    }
                )
                await send_with_request_id({"type": "http.response.body", "body": body})
