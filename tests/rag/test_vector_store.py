"""P5-2: fake embeddings and the in-memory vector store."""

import math

import pytest

from rag.chunking import chunk_article
from rag.vector_store import (
    DEFAULT_DIMENSIONS,
    FakeEmbeddings,
    InMemoryVectorStore,
    get_embeddings,
    get_vector_store,
    reset_vector_store,
)


def test_embeddings_are_384_dim_unit_length_and_deterministic():
    emb = FakeEmbeddings()
    first = emb.embed_query("reset my authenticator")
    assert len(first) == DEFAULT_DIMENSIONS == 384
    assert math.isclose(sum(v * v for v in first), 1.0, rel_tol=1e-9)
    assert first == FakeEmbeddings().embed_query("reset my authenticator")


def test_similar_text_scores_higher_than_unrelated():
    emb = FakeEmbeddings()
    a, b, c = (emb.embed_query(t) for t in ("refund seats", "refund for seats", "dark mode"))
    dot = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))
    assert dot(a, b) > dot(a, c)


def test_empty_text_gives_zero_vector():
    assert not any(FakeEmbeddings().embed_query("the and of"))


def test_unknown_embedding_provider_is_rejected():
    with pytest.raises(ValueError, match="not implemented"):
        get_embeddings("openai")


async def test_add_search_count_delete(articles):
    store = InMemoryVectorStore()
    chunks = [c for a in articles for c in chunk_article(a)]
    assert await store.add_documents(chunks) == len(chunks) == await store.count()
    hits = await store.search("locked out wrong MFA code authenticator", top_k=3)
    assert hits[0].chunk.slug == "mfa-recovery"
    assert hits == sorted(hits, key=lambda h: -h.score)

    mfa_id = hits[0].chunk.article_id
    removed = await store.delete([mfa_id])
    assert removed >= 1 and await store.count() == len(chunks) - removed
    assert await store.delete(None) == len(chunks) - removed
    assert await store.count() == 0
    assert await store.health() is True


async def test_search_filters_by_category(store):
    hits = await store.search("refund", top_k=20, category="billing")
    assert hits and {h.chunk.category for h in hits} == {"billing"}
    assert {c.category for c in await store.list_chunks("security")} == {"security"}


async def test_adding_twice_does_not_duplicate(articles):
    store = InMemoryVectorStore()
    chunks = chunk_article(articles[0])
    await store.add_documents(chunks)
    await store.add_documents(chunks)
    assert await store.count() == len(chunks)


def test_factory_returns_one_memory_store_per_process():
    reset_vector_store()
    assert get_vector_store() is get_vector_store()
    assert isinstance(get_vector_store(), InMemoryVectorStore)
