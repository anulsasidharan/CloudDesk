"""Short-term memory: per-ticket conversation and workflow state in Redis, 24 h TTL.

The RAG retrieval cache (``rag:{mode}:{category}:{top_k}:{query}``, 300 s) is owned by
``rag.retriever``; its key builder and TTL are re-exported here so there is one documented list of
what lives in Redis. Every call fails soft: Redis being down must never break a run.
"""

import json
import logging
from typing import Any

from app.core.guardrails import scrub

from rag.retriever import CACHE_TTL_SECONDS as RETRIEVAL_CACHE_TTL_SECONDS
from rag.retriever import cache_key as retrieval_cache_key

SHORT_TERM_TTL_SECONDS = 24 * 60 * 60
MAX_CONVERSATION_MESSAGES = 50
MAX_MESSAGE_CHARS = 2000

__all__ = [
    "MAX_CONVERSATION_MESSAGES",
    "RETRIEVAL_CACHE_TTL_SECONDS",
    "SHORT_TERM_TTL_SECONDS",
    "ShortTermMemory",
    "retrieval_cache_key",
]

_log = logging.getLogger("memory.short_term")


def conversation_key(ticket_id: str) -> str:
    return f"conv:{ticket_id}"


def workflow_state_key(ticket_id: str) -> str:
    return f"wfstate:{ticket_id}"


class ShortTermMemory:
    def __init__(self, redis: Any | None = None) -> None:
        self._redis = redis

    @property
    def redis(self) -> Any:
        if self._redis is None:
            from app.core.redis import get_redis

            self._redis = get_redis()
        return self._redis

    async def append_message(self, ticket_id: str, role: str, content: str) -> bool:
        """Add one turn (scrubbed, truncated). Keeps the newest 50. Returns False on Redis error."""
        entry = json.dumps({"role": role, "content": scrub(content)[:MAX_MESSAGE_CHARS]})
        key = conversation_key(ticket_id)
        try:
            await self.redis.rpush(key, entry)
            await self.redis.ltrim(key, -MAX_CONVERSATION_MESSAGES, -1)
            await self.redis.expire(key, SHORT_TERM_TTL_SECONDS)
            return True
        except Exception:  # noqa: BLE001 - memory is advisory
            _log.warning("short-term append failed", exc_info=True)
            return False

    async def get_conversation(self, ticket_id: str) -> list[dict[str, str]]:
        try:
            raw = await self.redis.lrange(conversation_key(ticket_id), 0, -1)
            return [json.loads(item) for item in raw]
        except Exception:  # noqa: BLE001
            _log.warning("short-term read failed", exc_info=True)
            return []

    async def save_workflow_state(self, ticket_id: str, state: dict[str, Any]) -> bool:
        try:
            payload = scrub(json.dumps(state, default=str))
            await self.redis.set(workflow_state_key(ticket_id), payload, ex=SHORT_TERM_TTL_SECONDS)
            return True
        except Exception:  # noqa: BLE001
            _log.warning("short-term state save failed", exc_info=True)
            return False

    async def get_workflow_state(self, ticket_id: str) -> dict[str, Any] | None:
        try:
            raw = await self.redis.get(workflow_state_key(ticket_id))
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            _log.warning("short-term state read failed", exc_info=True)
            return None

    async def clear(self, ticket_id: str) -> None:
        try:
            await self.redis.delete(conversation_key(ticket_id), workflow_state_key(ticket_id))
        except Exception:  # noqa: BLE001
            _log.warning("short-term clear failed", exc_info=True)
