"""``/knowledge`` routes. HTTP, auth and RBAC only."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import AuthUser, require_role
from app.schemas.common import Category, Role
from app.schemas.knowledge import (
    ArticleDetail,
    ArticleOut,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
)
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
VIEWER = Depends(require_role(Role.VIEWER))
ADMIN = Depends(require_role(Role.ADMIN))


@router.get("/articles", response_model=list[ArticleOut])
async def list_articles(
    search: str = Query("", max_length=200),
    category: Category | None = None,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> list[ArticleOut]:
    return await knowledge_service.list_articles(
        session, search=search, category=category.value if category else None
    )


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: str,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> ArticleDetail:
    try:
        return await knowledge_service.get_article(session, article_id)
    except knowledge_service.ArticleNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found") from exc


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(body: SearchRequest, _: AuthUser = VIEWER) -> SearchResponse:
    return await knowledge_service.search(body)


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_knowledge(
    _: AuthUser = ADMIN, session: AsyncSession = Depends(get_session)
) -> ReindexResponse:
    return await knowledge_service.reindex(session)
