"""P5-3: hybrid retrieval.

semantic search  ┐
                 ├─> reciprocal rank fusion (k=60) -> heuristic rerank -> optional LLM rerank
keyword (BM25)   ┘                                          -> one hit per article -> top_k

Results are cached in Redis for 300 seconds under ``rag:{mode}:{category}:{top_k}:{query}``.
The cache is advisory: any Redis error falls through to a live search.
"""

import json
import math
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from rag.chunking import Chunk
from rag.text import tokenize
from rag.vector_store import VectorStoreService, get_vector_store

Mode = Literal["hybrid", "semantic", "keyword"]
MODES: tuple[str, ...] = ("hybrid", "semantic", "keyword")

RRF_K = 60
CANDIDATES = 20
CACHE_TTL_SECONDS = 300
CACHE_PREFIX = "rag:"
CATEGORY_BOOST = 0.01
TITLE_BOOST = 0.02
SNIPPET_CHARS = 240


@dataclass(frozen=True)
class Evidence:
    """One cited piece of knowledge (shape fixed by CLAUDE.md section 8)."""

    id: str
    title: str
    source: str
    snippet: str
    score: float
    url: str
    article_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Reranker = Callable[[str, list[Evidence]], Awaitable[list[Evidence]]]


class BM25:
    """Okapi BM25 over chunk text. Small and dependency-free; built per call (the corpus is tiny)."""

    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = list(chunks)
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c.text)) for c in self.chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        frequency: Counter[str] = Counter()
        for doc in self.docs:
            frequency.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in frequency.items()}

    def search(self, query: str, top_k: int) -> list[tuple[Chunk, float]]:
        terms = set(tokenize(query))
        scored: list[tuple[Chunk, float]] = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                score += self.idf[term] * tf * (self.k1 + 1) / norm
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return scored[:top_k]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """Merge ranked id lists. An id's score is the sum of ``1 / (k + rank)`` over the lists."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
    return fused


def heuristic_rerank(
    query: str,
    scores: dict[str, float],
    chunks: dict[str, Chunk],
    category_hint: str | None = None,
) -> dict[str, float]:
    """Nudge fused scores: a chunk from the hinted category, and chunks whose article title
    shares words with the query, move up. Boosts are small next to an RRF gap of one rank."""
    query_terms = set(tokenize(query))
    adjusted = {}
    for chunk_id, score in scores.items():
        chunk = chunks[chunk_id]
        boost = CATEGORY_BOOST if category_hint and chunk.category == category_hint else 0.0
        title_terms = set(tokenize(chunk.title))
        if query_terms and title_terms:
            boost += TITLE_BOOST * len(query_terms & title_terms) / len(title_terms)
        adjusted[chunk_id] = score + boost
    return adjusted


def _snippet(chunk: Chunk) -> str:
    text = " ".join(chunk.content.split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rstrip() + "…"


def _evidence(chunk: Chunk, score: float) -> Evidence:
    return Evidence(
        id=chunk.id,
        title=chunk.title,
        source=chunk.source,
        snippet=_snippet(chunk),
        score=round(score, 4),
        url=f"/knowledge/{chunk.article_id}",
        article_id=chunk.article_id,
    )


def cache_key(mode: str, category: str | None, top_k: int, query: str) -> str:
    return f"{CACHE_PREFIX}{mode}:{category or 'any'}:{top_k}:{query.strip()}"


async def invalidate_cache(cache: Any | None = None) -> int:
    """Drop every cached retrieval (after a reindex the old answers are stale)."""
    try:
        cache = cache if cache is not None else _default_cache()
        keys = [key async for key in cache.scan_iter(match=f"{CACHE_PREFIX}*")]
        return int(await cache.delete(*keys)) if keys else 0
    except Exception:  # noqa: BLE001 - cache is advisory
        return 0


def _default_cache() -> Any:
    from app.core.redis import get_redis

    return get_redis()


async def retrieve(
    query: str,
    *,
    mode: Mode = "hybrid",
    top_k: int = 5,
    category: str | None = None,
    category_hint: str | None = None,
    store: VectorStoreService | None = None,
    cache: Any | None = None,
    use_cache: bool = True,
    reranker: Reranker | None = None,
) -> list[Evidence]:
    """Find the best ``top_k`` articles for ``query``, one chunk per article.

    ``category`` is a hard filter. ``category_hint`` only nudges ranking (the Knowledge Agent
    passes the ticket's classified category). ``reranker`` is the optional LLM rerank hook.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    query = query.strip()
    if not query:
        return []

    key = cache_key(mode, category, top_k, query)
    if use_cache and reranker is None:
        cache = cache if cache is not None else _safe_default_cache()
        cached = await _cache_get(cache, key)
        if cached is not None:
            return cached

    store = store or get_vector_store()
    rankings: list[list[str]] = []
    chunks: dict[str, Chunk] = {}

    if mode in ("hybrid", "semantic"):
        hits = await store.search(query, top_k=CANDIDATES, category=category)
        rankings.append([h.chunk.id for h in hits])
        chunks.update({h.chunk.id: h.chunk for h in hits})
    if mode in ("hybrid", "keyword"):
        corpus = await store.list_chunks(category)
        keyword_hits = BM25(corpus).search(query, CANDIDATES)
        rankings.append([c.id for c, _ in keyword_hits])
        chunks.update({c.id: c for c, _ in keyword_hits})

    scores = heuristic_rerank(query, reciprocal_rank_fusion(rankings), chunks, category_hint)

    best: dict[str, tuple[str, float]] = {}  # article id -> (chunk id, score)
    for chunk_id, score in scores.items():
        article_id = chunks[chunk_id].article_id
        if article_id not in best or score > best[article_id][1]:
            best[article_id] = (chunk_id, score)
    ordered = sorted(best.values(), key=lambda item: (-item[1], item[0]))
    results = [_evidence(chunks[cid], score) for cid, score in ordered]

    if reranker is not None:
        results = await reranker(query, results)
    results = results[:top_k]

    if use_cache and reranker is None:
        await _cache_set(cache, key, results)
    return results


def _safe_default_cache() -> Any | None:
    try:
        return _default_cache()
    except Exception:  # noqa: BLE001 - cache is advisory
        return None


async def _cache_get(cache: Any | None, key: str) -> list[Evidence] | None:
    if cache is None:
        return None
    try:
        raw = await cache.get(key)
        return [Evidence(**item) for item in json.loads(raw)] if raw else None
    except Exception:  # noqa: BLE001 - cache is advisory
        return None


async def _cache_set(cache: Any | None, key: str, results: list[Evidence]) -> None:
    if cache is None:
        return
    try:
        await cache.set(key, json.dumps([r.to_dict() for r in results]), ex=CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - cache is advisory
        return
