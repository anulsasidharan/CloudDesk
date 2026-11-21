"""P5-4: build the index. Chunk every article, embed, store; reindex recreates the collection."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rag.chunking import Chunk, chunk_article
from rag.retriever import invalidate_cache
from rag.vector_store import VectorStoreService, get_vector_store


@dataclass(frozen=True)
class IngestResult:
    articles: int
    chunks: int


async def ingest_articles(
    articles: Sequence[Mapping[str, Any]],
    store: VectorStoreService | None = None,
    *,
    recreate: bool = True,
    cache: Any | None = None,
) -> IngestResult:
    """Index ``articles`` (records with ``id, slug, title, category, body``).

    ``recreate=True`` empties the collection first, so a deleted or renamed article cannot linger.
    Cached retrievals are dropped either way because their answers may now be wrong.
    """
    store = store or get_vector_store()
    chunks: list[Chunk] = [chunk for article in articles for chunk in chunk_article(article)]
    if recreate:
        await store.delete(None)
    await store.add_documents(chunks)
    await invalidate_cache(cache)
    return IngestResult(articles=len(articles), chunks=len(chunks))
