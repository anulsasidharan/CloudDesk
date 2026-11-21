"""Chunk and index the knowledge base (``make ingest``), then prove retrieval works.

Loads the demo data if the database is empty, rebuilds the index from ``support_articles``,
and runs the CD-1012 checkpoint: the MFA recovery article must be in the top 3.
With ``VECTOR_STORE=memory`` the index lives only for this process (a check, not a deploy step);
with Qdrant it persists.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.core.database import create_tables, dispose_engine, session_scope
from app.core.redis import close_redis
from app.repositories import TicketRepository
from app.services import knowledge_service
from app.services.seed_service import bootstrap_demo_data

from rag.retriever import retrieve

EXPECTED_SLUG = "mfa-recovery"


async def main() -> int:
    await create_tables()
    await bootstrap_demo_data()
    async with session_scope() as session:
        result = await knowledge_service.reindex(session)
        ticket = await TicketRepository(session).get_by_number("CD-1012")
    print(f"indexed {result.articles} articles into {result.indexed} chunks")
    if ticket is None:
        print("CD-1012 is missing")
        return 1
    hits = await retrieve(f"{ticket.subject} {ticket.body}", top_k=3, use_cache=False)
    for rank, hit in enumerate(hits, start=1):
        print(f"  {rank}. {hit.source}  score={hit.score}")
    found = any(hit.source.startswith(f"kb://{EXPECTED_SLUG}#") for hit in hits)
    print(f"CD-1012 -> {EXPECTED_SLUG} in top 3: {'yes' if found else 'NO'}")
    await dispose_engine()
    await close_redis()
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
