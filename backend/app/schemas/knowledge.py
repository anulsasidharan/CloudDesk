"""Knowledge routes (``docs/API_CONTRACT.md``, Knowledge base)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Category


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    category: str
    tags: list[str]
    summary: str
    updated_at: datetime


class ArticleDetail(ArticleOut):
    content: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    category: Category | None = None


class EvidenceOut(BaseModel):
    id: str
    title: str
    source: str
    snippet: str
    score: float
    url: str
    article_id: str


class SearchResponse(BaseModel):
    results: list[EvidenceOut]
    mode: str
    took_ms: float


class ReindexResponse(BaseModel):
    indexed: int  # chunks written
    articles: int
