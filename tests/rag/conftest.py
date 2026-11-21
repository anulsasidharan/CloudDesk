"""Shared fixtures: the real 15 articles, indexed into a private in-memory store."""

import pytest
from app.services.seed_service import load_article_files, resolve_data_dir

from rag.ingest import ingest_articles
from rag.vector_store import InMemoryVectorStore


@pytest.fixture(scope="session")
def articles() -> list[dict]:
    return load_article_files(resolve_data_dir())


@pytest.fixture(scope="session")
async def store(articles) -> InMemoryVectorStore:
    private = InMemoryVectorStore()
    await ingest_articles(articles, private, cache=None)
    return private
