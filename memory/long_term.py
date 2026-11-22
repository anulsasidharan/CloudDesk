"""Long-term memory: durable, scrubbed, de-duplicated customer notes in ``customer_memory``.

The single writer of that table. Kinds: preference, past_issue, troubleshooting, note.
"""

from dataclasses import dataclass

from app.core.guardrails import scrub
from app.repositories import CustomerMemoryRepository
from app.repositories.people import MAX_RECALL
from app.schemas.common import MemoryKind
from sqlalchemy.ext.asyncio import AsyncSession

MAX_NOTE_CHARS = 500


@dataclass(frozen=True)
class MemoryNote:
    id: str
    kind: str
    content: str
    source_ticket_id: str | None


class LongTermMemory:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CustomerMemoryRepository(session)

    async def recall(self, customer_id: str, *, limit: int = MAX_RECALL) -> list[MemoryNote]:
        """Newest notes first, at most 10."""
        rows = await self._repo.recall(customer_id, limit=limit)
        return [MemoryNote(r.id, r.kind, r.content, r.source_ticket_id) for r in rows]

    async def remember(
        self,
        customer_id: str,
        kind: str | MemoryKind,
        content: str,
        *,
        source_ticket_id: str | None = None,
    ) -> MemoryNote | None:
        """Scrub, trim and store. ``None`` when empty or an exact duplicate already exists."""
        kind_value = MemoryKind(kind).value
        clean = " ".join(scrub(content).split())[:MAX_NOTE_CHARS].strip()
        if not clean:
            return None
        row = await self._repo.add_note(
            customer_id, kind_value, clean, source_ticket_id=source_ticket_id
        )
        if row is None:
            return None
        return MemoryNote(row.id, row.kind, row.content, row.source_ticket_id)
