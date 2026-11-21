"""Fixed-window rate limit per client, backed by Redis (N2).

One counter per ``(client, minute)``. The first hit in a window sets a 60-second expiry, so keys
clean themselves up. If Redis is unreachable the request is allowed (fail open) and the error is
logged: a cache outage must not take the support console down. Health probes are never limited.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.redis import get_redis

WINDOW_SECONDS = 60
EXEMPT_PREFIXES = ("/health",)
_logger = logging.getLogger("app.middleware.rate_limit")


def client_key(scope: Scope) -> str:
    """Client identity: the first ``X-Forwarded-For`` hop (behind a load balancer) or the socket IP."""
    for name, value in scope.get("headers", []):
        if name.lower() == b"x-forwarded-for":
            first = value.decode("latin-1").split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int | None = None,
        redis_factory: Callable[[], Any] = get_redis,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self._limit = limit
        self._redis_factory = redis_factory
        self._clock = clock

    def _current_limit(self) -> int:
        return self._limit if self._limit is not None else get_settings().rate_limit_per_minute

    async def _hit(self, key: str) -> int:
        redis = self._redis_factory()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, WINDOW_SECONDS + 5)
        return int(count)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        limit = self._current_limit()
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        retry_after = int(WINDOW_SECONDS - (now % WINDOW_SECONDS)) or 1
        try:
            count = await self._hit(f"rl:{client_key(scope)}:{window}")
        except Exception:
            _logger.exception("rate limiter unavailable; allowing request")
            await self.app(scope, receive, send)
            return

        remaining = max(limit - count, 0)
        if count > limit:
            body = json.dumps({"detail": "Rate limit exceeded"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"retry-after", str(retry_after).encode("ascii")),
                        (b"x-ratelimit-limit", str(limit).encode("ascii")),
                        (b"x-ratelimit-remaining", b"0"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(limit)
                headers["X-RateLimit-Remaining"] = str(remaining)
            await send(message)

        await self.app(scope, receive, send_with_headers)
