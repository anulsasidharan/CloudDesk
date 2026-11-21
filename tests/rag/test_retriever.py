"""P5-3: modes, RRF, rerank, filters, one-hit-per-article, cache."""

import fakeredis
import pytest

from rag.chunking import Chunk
from rag.retriever import (
    BM25,
    CACHE_PREFIX,
    cache_key,
    heuristic_rerank,
    invalidate_cache,
    reciprocal_rank_fusion,
    retrieve,
)

MFA_QUERY = "Locked out after too many MFA attempts wrong code old authenticator"


async def _slugs(store, query, **kwargs):
    kwargs.setdefault("use_cache", False)
    return [e.source.split("#")[0].removeprefix("kb://") for e in await retrieve(query, store=store, **kwargs)]


@pytest.mark.parametrize("mode", ["hybrid", "semantic", "keyword"])
async def test_every_mode_finds_the_mfa_article(store, mode):
    assert "mfa-recovery" in (await _slugs(store, MFA_QUERY, mode=mode, top_k=3))


async def test_unknown_mode_and_bad_top_k_are_rejected(store):
    with pytest.raises(ValueError):
        await retrieve("x", mode="vibes", store=store, use_cache=False)
    with pytest.raises(ValueError):
        await retrieve("x", top_k=0, store=store, use_cache=False)


async def test_blank_query_returns_nothing(store):
    assert await retrieve("   ", store=store, use_cache=False) == []


async def test_one_hit_per_article_and_evidence_shape(store):
    results = await retrieve("refund seats billing proration", top_k=10, store=store, use_cache=False)
    article_ids = [e.article_id for e in results]
    assert len(article_ids) == len(set(article_ids))
    first = results[0]
    assert first.source.startswith("kb://") and "#" in first.source
    assert first.url == f"/knowledge/{first.article_id}"
    assert first.snippet and isinstance(first.score, float)
    assert [e.score for e in results] == sorted((e.score for e in results), reverse=True)


async def test_category_filter_is_hard(store):
    results = await retrieve("refund", top_k=10, category="billing", store=store, use_cache=False)
    assert results
    chunks = {c.id: c for c in await store.list_chunks()}
    assert {chunks[e.id].category for e in results} == {"billing"}


def test_rrf_rewards_agreement_between_lists():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] > fused["c"] and fused["d"] < fused["a"]
    assert reciprocal_rank_fusion([]) == {}


def test_rerank_boosts_category_and_title_overlap():
    def chunk(cid, title, category):
        return Chunk(cid, "art-" + cid, cid, title, category, "h", "body", 0)

    chunks = {"x": chunk("x", "Refund policy", "billing"), "y": chunk("y", "Dark mode", "other")}
    scores = {"x": 0.016, "y": 0.0165}
    plain = heuristic_rerank("refund please", scores, chunks)
    hinted = heuristic_rerank("refund please", scores, chunks, category_hint="billing")
    assert plain["x"] > plain["y"]  # title overlap alone flips the order
    assert hinted["x"] > plain["x"]


def test_bm25_prefers_the_chunk_with_the_rare_term():
    def chunk(cid, text):
        return Chunk(cid, cid, cid, "T", "other", "H", text, 0)

    bm25 = BM25([chunk("a", "invoice seat proration"), chunk("b", "dark mode theme"), chunk("c", "seat")])
    top = bm25.search("proration seat", 3)
    assert top[0][0].id == "a"
    assert bm25.search("zzzz", 3) == []


async def test_results_are_cached_then_served_without_searching(store):
    cache = fakeredis.FakeAsyncRedis(decode_responses=True)

    class Spy:
        calls = 0

        async def search(self, *a, **k):
            Spy.calls += 1
            return await store.search(*a, **k)

        async def list_chunks(self, *a, **k):
            return await store.list_chunks(*a, **k)

    first = await retrieve(MFA_QUERY, store=Spy(), cache=cache, top_k=3)
    assert Spy.calls == 1
    assert await cache.ttl(cache_key("hybrid", None, 3, MFA_QUERY)) in range(1, 301)
    second = await retrieve(MFA_QUERY, store=Spy(), cache=cache, top_k=3)
    assert Spy.calls == 1 and second == first

    assert await invalidate_cache(cache) == 1
    assert not [k async for k in cache.scan_iter(match=f"{CACHE_PREFIX}*")]


async def test_broken_cache_falls_back_to_live_search(store):
    class Broken:
        async def get(self, *_):
            raise ConnectionError("redis down")

        set = get

    assert await retrieve(MFA_QUERY, store=store, cache=Broken(), top_k=3)


async def test_llm_rerank_hook_can_reorder(store):
    async def reverse(_query, results):
        return list(reversed(results))

    plain = await retrieve(MFA_QUERY, store=store, top_k=3, use_cache=False)
    flipped = await retrieve(MFA_QUERY, store=store, top_k=3, use_cache=False, reranker=reverse)
    assert flipped[0].article_id != plain[0].article_id
