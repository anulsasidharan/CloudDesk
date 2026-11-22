"""Recall before a run, record after it. The two calls the workflow nodes will make (Phase 10)."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from memory.long_term import LongTermMemory, MemoryNote
from memory.short_term import ShortTermMemory

MAX_TROUBLESHOOTING_STEPS = 3


@dataclass(frozen=True)
class RecordResult:
    written: int
    skipped_duplicates: int


class MemoryService:
    def __init__(self, session: AsyncSession, short_term: ShortTermMemory | None = None) -> None:
        self.long_term = LongTermMemory(session)
        self.short_term = short_term or ShortTermMemory()

    async def recall_customer(self, customer_id: str) -> list[MemoryNote]:
        """Up to 10 newest notes for this customer only."""
        return await self.long_term.recall(customer_id)

    async def record_resolution(
        self,
        customer_id: str,
        ticket_id: str,
        *,
        issue_summary: str,
        troubleshooting_steps: Sequence[str],
        resolution_summary: str,
    ) -> RecordResult:
        """Write a past issue, the first 3 troubleshooting steps and a resolution note.

        Callers pass the one-line summary and plan text, never the raw ticket body. Everything is
        scrubbed, and exact duplicates (same customer, kind, text) are skipped, so re-running a
        ticket does not pile up notes.
        """
        items: list[tuple[str, str]] = [("past_issue", issue_summary)]
        items += [("troubleshooting", s) for s in troubleshooting_steps[:MAX_TROUBLESHOOTING_STEPS]]
        items.append(("note", f"Resolution: {resolution_summary}"))
        written = skipped = 0
        for kind, content in items:
            note = await self.long_term.remember(
                customer_id, kind, content, source_ticket_id=ticket_id
            )
            if note is None:
                skipped += 1
            else:
                written += 1
        return RecordResult(written, skipped)
