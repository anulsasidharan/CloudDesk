"""Knowledge use cases (F5): browse articles, search the index, rebuild the index.

Articles live in ``support_articles``; their chunks live in the vector store. This service is
the bridge, so ``rag/`` never touches the database and the repositories never touch the index.
"""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.repositories import SupportArticleRepository
from app.schemas.knowledge import (
    ArticleDetail,
    ArticleOut,
    EvidenceOut,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
)
from rag.ingest import ingest_articles
from rag.retriever import retrieve
from rag.vector_store import get_vector_store

logger = logging.getLogger("app.knowledge")


class ArticleNotFoundError(LookupError):
    pass


def _record(article) -> dict:
    return {
        "id": article.id,
        "slug": article.slug,
        "title": article.title,
        "category": article.category,
        "body": article.body,
    }


async def list_articles(
    session: AsyncSession, *, search: str = "", category: str | None = None
) -> list[ArticleOut]:
    rows = await SupportArticleRepository(session).search(search, category)
    return [ArticleOut.model_validate(row) for row in rows]


async def get_article(session: AsyncSession, key: str) -> ArticleDetail:
    article = await SupportArticleRepository(session).get_by_id_or_slug(key)
    if article is None:
        raise ArticleNotFoundError(key)
    return ArticleDetail(**ArticleOut.model_validate(article).model_dump(), content=article.body)


async def reindex(session: AsyncSession) -> ReindexResponse:
    """Recreate the collection from every article in the database."""
    articles = await SupportArticleRepository(session).search()
    result = await ingest_articles([_record(a) for a in articles], recreate=True)
    return ReindexResponse(indexed=result.chunks, articles=result.articles)


async def ensure_indexed() -> bool:
    """Index on first use when the store is empty (a fresh process, or an empty Qdrant)."""
    if await get_vector_store().count() > 0:
        return False
    async with session_scope() as session:
        result = await reindex(session)
    logger.info("knowledge index built", extra={"chunks": result.indexed})
    return result.indexed > 0


async def search(request: SearchRequest) -> SearchResponse:
    await ensure_indexed()
    started = time.perf_counter()
    evidence = await retrieve(
        request.query,
        mode=request.mode,
        top_k=request.top_k,
        category=request.category.value if request.category else None,
    )
    return SearchResponse(
        results=[EvidenceOut(**e.to_dict()) for e in evidence],
        mode=request.mode,
        took_ms=round((time.perf_counter() - started) * 1000, 2),
    )
