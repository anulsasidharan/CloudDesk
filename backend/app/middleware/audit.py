"""Write one ``audit_logs`` row for every state-changing request (N6).

Runs innermost (after CORS, RequestId and RateLimit) so it sees the final status of the route.
It records who (from the bearer token, if valid), what (method + path), the status code and the
request id. It never stores request bodies, query strings or tokens. A failure to write the row is
logged and swallowed: auditing must not turn a successful request into an error.
"""

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.database import session_scope
from app.core.security import TokenError, bearer_token, decode_token
from app.repositories.audit import AuditRepository

AUDITED_EXEMPT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_logger = logging.getLogger("app.middleware.audit")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in AUDITED_EXEMPT_METHODS:
            await self.app(scope, receive, send)
            return

        status_code = 500

        async def capture(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            await self._record(scope, status_code)

    async def _record(self, scope: Scope, status_code: int) -> None:
        actor_id = actor_email = actor_role = None
        token = bearer_token(_header(scope, b"authorization"))
        if token:
            try:
                user = decode_token(token)
            except TokenError:
                pass
            else:
                actor_id, actor_email, actor_role = user.id, user.email, user.role
        state = scope.get("state") or {}
        request_id = state.get("request_id") if isinstance(state, dict) else None
        try:
            async with session_scope() as session:
                await AuditRepository(session).add(
                    actor_id=actor_id,
                    actor_email=actor_email,
                    method=scope["method"],
                    path=scope["path"][:500],
                    status_code=status_code,
                    request_id=request_id,
                    detail={"actor_role": actor_role},
                )
        except Exception:
            _logger.exception("could not write audit log")
