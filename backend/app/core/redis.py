"""One async Redis client for the process: fakeredis offline, real Redis when ``REDIS_URL`` is set."""

import logging
from typing import Any

from app.core.config import get_settings

_clients: dict[str, Any] = {}


def get_redis() -> Any:
    """Return the cached async client for the current settings.

    Keyed by the Redis URL (or ``fake``) so a test that changes settings gets a fresh client.
    """
    settings = get_settings()
    key = "fake" if settings.uses_fake_redis else settings.redis_url.strip()
    client = _clients.get(key)
    if client is None:
        if settings.uses_fake_redis:
            import fakeredis

            client = fakeredis.FakeAsyncRedis(decode_responses=True)
        else:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.redis_url.strip(), decode_responses=True)
        _clients[key] = client
    return client


async def close_redis() -> None:
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:  # shutdown must not fail on a dead connection
            logging.getLogger("app.core.redis").warning("redis close failed", exc_info=True)
