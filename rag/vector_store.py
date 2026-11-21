"""P5-2: embeddings and the vector store.

``VectorStoreService`` is the only thing the rest of the code knows. ``InMemoryVectorStore`` runs
offline; ``QdrantVectorStore`` is the cloud implementation. ``VECTOR_STORE`` picks one.
"""

import hashlib
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from rag.chunking import Chunk
from rag.text import tokenize

DEFAULT_DIMENSIONS = 384


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class FakeEmbeddings:
    """Hashed bag-of-words vectors. No network, no model, same output on every machine.

    Each word is hashed (blake2b, not ``hash()``, which changes per process) into one of
    ``dimensions`` buckets with a +/- sign, then the vector is scaled to length 1. Texts that
    share words point in similar directions, which is all the offline demo needs.
    """

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


def get_embeddings(provider: str | None = None, dimensions: int | None = None) -> FakeEmbeddings:
    from app.core.config import get_settings

    settings = get_settings()
    name = provider or settings.embedding_provider
    if name != "fake":
        raise ValueError(f"EMBEDDING_PROVIDER={name!r} is not implemented yet; use 'fake'")
    return FakeEmbeddings(dimensions or settings.embedding_dimensions)


class VectorStoreService(Protocol):
    """What retrieval needs from a store. Chunks go in as text; the store embeds them."""

    async def add_documents(self, chunks: Sequence[Chunk]) -> int: ...

    async def search(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[ScoredChunk]: ...

    async def delete(self, article_ids: Sequence[str] | None = None) -> int:
        """Remove the chunks of these articles, or recreate the whole collection when ``None``."""
        ...

    async def count(self) -> int: ...

    async def health(self) -> bool: ...

    async def list_chunks(self, category: str | None = None) -> list[Chunk]:
        """Every stored chunk. Keyword search builds its index from this."""
        ...


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class InMemoryVectorStore:
    """Dict of ``chunk id -> (chunk, vector)``. Cosine similarity is a dot product on unit vectors."""

    def __init__(self, embeddings: FakeEmbeddings | None = None) -> None:
        self.embeddings = embeddings or FakeEmbeddings()
        self._items: dict[str, tuple[Chunk, list[float]]] = {}

    async def add_documents(self, chunks: Sequence[Chunk]) -> int:
        vectors = self.embeddings.embed_documents([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._items[chunk.id] = (chunk, vector)
        return len(chunks)

    async def search(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[ScoredChunk]:
        query_vector = self.embeddings.embed_query(query)
        scored = [
            ScoredChunk(chunk, _dot(query_vector, vector))
            for chunk, vector in self._items.values()
            if category is None or chunk.category == category
        ]
        scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: (-s.score, s.chunk.id))
        return scored[:top_k]

    async def delete(self, article_ids: Sequence[str] | None = None) -> int:
        if article_ids is None:
            removed = len(self._items)
            self._items.clear()
            return removed
        wanted = set(article_ids)
        doomed = [cid for cid, (chunk, _) in self._items.items() if chunk.article_id in wanted]
        for chunk_id in doomed:
            del self._items[chunk_id]
        return len(doomed)

    async def count(self) -> int:
        return len(self._items)

    async def health(self) -> bool:
        return True

    async def list_chunks(self, category: str | None = None) -> list[Chunk]:
        chunks = [chunk for chunk, _ in self._items.values()]
        if category is not None:
            chunks = [c for c in chunks if c.category == category]
        return sorted(chunks, key=lambda c: c.id)


class QdrantVectorStore:
    """Qdrant over HTTP. Needs ``qdrant-client`` (not a default dependency) and a running server.

    NOT exercised by the offline tests; it has never been run against a real Qdrant.
    """

    def __init__(
        self,
        url: str,
        api_key: str = "",
        collection: str = "clouddesk_knowledge",
        embeddings: FakeEmbeddings | None = None,
    ) -> None:
        try:
            from qdrant_client import AsyncQdrantClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("VECTOR_STORE=qdrant needs: uv add qdrant-client") from exc
        self.embeddings = embeddings or FakeEmbeddings()
        self.collection = collection
        self._client: Any = AsyncQdrantClient(url=url, api_key=api_key or None)
        self._ready = False

    async def _ensure_collection(self) -> None:
        if self._ready:
            return
        from qdrant_client.models import Distance, VectorParams

        if not await self._client.collection_exists(self.collection):
            await self._client.create_collection(
                self.collection,
                vectors_config=VectorParams(size=self.embeddings.dimensions, distance=Distance.COSINE),
            )
        self._ready = True

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    async def add_documents(self, chunks: Sequence[Chunk]) -> int:
        from qdrant_client.models import PointStruct

        await self._ensure_collection()
        vectors = self.embeddings.embed_documents([c.text for c in chunks])
        points = [
            PointStruct(id=self._point_id(c.id), vector=v, payload=c.to_payload())
            for c, v in zip(chunks, vectors, strict=True)
        ]
        if points:
            await self._client.upsert(self.collection, points=points)
        return len(points)

    async def search(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[ScoredChunk]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure_collection()
        flt = (
            Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])
            if category
            else None
        )
        response = await self._client.query_points(
            self.collection,
            query=self.embeddings.embed_query(query),
            limit=top_k,
            query_filter=flt,
            with_payload=True,
        )
        return [ScoredChunk(Chunk.from_payload(p.payload), float(p.score)) for p in response.points]

    async def delete(self, article_ids: Sequence[str] | None = None) -> int:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchAny

        removed = await self.count() if self._ready or article_ids is None else 0
        if article_ids is None:
            await self._client.delete_collection(self.collection)
            self._ready = False
            await self._ensure_collection()
            return removed
        await self._ensure_collection()
        selector = FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="article_id", match=MatchAny(any=list(article_ids)))]
            )
        )
        await self._client.delete(self.collection, points_selector=selector)
        return 0

    async def count(self) -> int:
        await self._ensure_collection()
        return int((await self._client.count(self.collection, exact=True)).count)

    async def health(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:  # noqa: BLE001 - health must not raise
            return False

    async def list_chunks(self, category: str | None = None) -> list[Chunk]:
        await self._ensure_collection()
        chunks: list[Chunk] = []
        offset = None
        while True:
            points, offset = await self._client.scroll(
                self.collection, limit=256, offset=offset, with_payload=True
            )
            chunks.extend(Chunk.from_payload(p.payload) for p in points)
            if offset is None:
                break
        if category is not None:
            chunks = [c for c in chunks if c.category == category]
        return sorted(chunks, key=lambda c: c.id)


_stores: dict[str, VectorStoreService] = {}


def get_vector_store() -> VectorStoreService:
    """One store per process, chosen by ``VECTOR_STORE``."""
    from app.core.config import get_settings

    settings = get_settings()
    key = "memory" if settings.vector_store == "memory" else f"qdrant:{settings.qdrant_url}"
    store = _stores.get(key)
    if store is None:
        embeddings = get_embeddings()
        if settings.vector_store == "memory":
            store = InMemoryVectorStore(embeddings)
        else:
            store = QdrantVectorStore(
                settings.qdrant_url,
                settings.qdrant_api_key.get_secret_value(),
                settings.qdrant_collection,
                embeddings,
            )
        _stores[key] = store
    return store


def reset_vector_store() -> None:
    """Forget the cached store (tests, or after a settings change)."""
    _stores.clear()
