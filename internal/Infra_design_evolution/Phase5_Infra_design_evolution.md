# Phase 5: Infrastructure Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 5: Knowledge pipeline.** This file explains how the knowledge pipeline is **wired** into the running application, which stores it talks to, how requests are routed to it, and what it means for the Docker and cloud setup in the final phase.

---

## Read this first: Phase 5 still has no Docker containers

There is no Dockerfile, Compose file or Terraform yet. The backend is one process on the developer's machine. Phase 5 adds **no new container, port or service**, but it does introduce the *shape* of two things the final phase must deploy: a **vector store** and a **Redis cache**. Offline, both run inside the same Python process.

| Decision in Phase 5 | Built? | Why Docker/cloud cares later |
|---|---|---|
| New `rag/` package at the repo root | Built | The backend image must copy `rag/` as well as `backend/`, and the Python path must include both |
| `/api/v1/knowledge/*` routes in the same FastAPI process | Built | Same port 8000, same load-balancer rule `/api/v1/*` |
| `VectorStoreService` with `VECTOR_STORE` = `memory` or `qdrant` | Built | In Compose this selects the `qdrant` service; in cloud, Qdrant Cloud |
| In-memory store (default) | Built | Per-process: each replica holds its own copy and must index at startup |
| `QdrantVectorStore` | **Written, never run** | Needs the `qdrant-client` package and a running server |
| Retrieval cache in Redis (`rag:*`, TTL 300 s) | Built (fakeredis offline) | Shared across replicas only with real Redis |
| Index built in the app lifespan | Built | Container start does a one-off index; health must not report ready before that if the index matters |
| Makefile `backend` target changed to run from the repo root | Built | Same import-path rule as the Dockerfile `WORKDIR` and `PYTHONPATH` |
| New environment variables | **None** | `EMBEDDING_*`, `VECTOR_STORE`, `QDRANT_*` were already in `.env.example` |
| Containers, network, volumes | **Not built** | Final phase |

---

## Step 1: The component wiring inside the process

```mermaid
flowchart LR
    B["Browser / curl"] -->|"HTTP :8000"| UV["uvicorn"]
    UV --> MW["CORS → RequestId → RateLimit → Audit"]
    MW --> KR["knowledge router<br/>/api/v1/knowledge"]
    KR --> KS["knowledge_service"]
    KS -->|"articles (SQL)"| DB[("SQLite file<br/>support_articles")]
    KS --> ING["rag.ingest"]
    KS --> RET["rag.retriever"]
    ING --> VS["VectorStoreService"]
    RET --> VS
    VS -->|"VECTOR_STORE=memory"| MEM["InMemoryVectorStore<br/>(RAM of this process)"]
    VS -.->|"VECTOR_STORE=qdrant"| QD[("Qdrant :6333")]:::future
    RET <-->|"cache rag:*"| FR[("fakeredis<br/>in-process")]
    MW <-->|"rate-limit counters"| FR
    classDef future stroke-dasharray: 5 5,fill:#eee,color:#666
```

Three stores, three jobs:

| Store | Holds | Offline | In the cloud |
|---|---|---|---|
| SQL database | The articles (source of truth) | SQLite file | Postgres / Supabase |
| Vector store | Chunks and their vectors (rebuildable) | RAM | Qdrant |
| Redis | Cached search results and rate-limit counters (disposable) | fakeredis in RAM | Redis |

Only the database is the source of truth. The vector store can always be rebuilt from it with `POST /knowledge/reindex`, and the cache can always be thrown away.

---

## Step 2: Request routing for a search

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant R as Router
    participant S as knowledge_service
    participant RC as Redis cache
    participant V as Vector store
    C->>MW: POST /api/v1/knowledge/search (Bearer JWT)
    MW->>MW: request id, rate limit, JWT role check, audit row
    MW->>R: viewer or higher
    R->>S: search(request)
    S->>V: count() = 0 ? index now
    S->>RC: GET rag:hybrid:any:5:query
    alt cache hit
        RC-->>S: Evidence[]
    else miss
        S->>V: semantic search (top 20)
        S->>V: list_chunks → BM25 (top 20)
        S->>S: RRF fuse, rerank, one per article
        S->>RC: SET ... EX 300
    end
    S-->>R: results, mode, took_ms
    R-->>C: 200
```

A `POST /search` is a non-GET request, so the Phase 3 audit middleware records it. That is fine for demo traffic; at scale you would exclude read-only POST searches from the audit table.

---

## Step 3: Startup and reindex

```mermaid
flowchart TD
    START["Process starts"] --> CT["create_tables()"]
    CT --> BOOT{"DEMO_MODE and<br/>DB empty?"}
    BOOT -->|yes| SEED["bootstrap_demo_data()<br/>15 articles → support_articles"]
    BOOT -->|no| IDX
    SEED --> IDX["ensure_indexed()"]
    IDX --> EMPTY{"vector store<br/>count == 0?"}
    EMPTY -->|yes| RE["reindex: read all articles,<br/>chunk, embed, store<br/>46 chunks"]
    EMPTY -->|no| SKIP["skip (Qdrant already filled)"]
    RE --> SERVE["serve requests"]
    SKIP --> SERVE
    IDX -.->|"exception"| WARN["log warning, still serve;<br/>first search retries"]
    WARN --> SERVE
```

```mermaid
flowchart LR
    ADM["POST /knowledge/reindex<br/>(admin JWT)"] --> DEL["store.delete(None)<br/>recreate collection"]
    DEL --> ADD["add_documents(all chunks)"]
    ADD --> INV["delete every rag:* cache key"]
    INV --> RES["{indexed: 46, articles: 15}"]
```

**Why it matters with several replicas.** With the in-memory store, every replica indexes itself at start, so a reindex call reaches only the replica that served it. With Qdrant, the index is shared and a reindex is global. This is a key reason the cloud profile uses `VECTOR_STORE=qdrant`.

---

## Step 4: Import paths: the one real change to how the app boots

`rag/` is at the repository root, next to `backend/`. Python must find both.

```mermaid
flowchart TD
    ROOT["repo root<br/>(on sys.path)"] --> RAG["rag/"]
    ROOT --> BE["backend/ (on sys.path)<br/>└─ app/"]
    ROOT --> SC["scripts/ingest.py<br/>inserts both paths itself"]
    ROOT --> TS["tests: pyproject pythonpath =<br/>['backend', '.']"]
    ROOT --> MK["make backend:<br/>python -m uvicorn app.main:app<br/>--app-dir backend"]
    DK["Dockerfile (final phase):<br/>COPY backend/ and rag/<br/>PYTHONPATH=/app:/app/backend"]:::future
    classDef future stroke-dasharray: 5 5,fill:#eee,color:#666
```

Before Phase 5 the server was started with `cd backend`, which put only `backend/` on the path. That would fail to import `rag`, so the Makefile now starts from the root with `python -m` (which adds the current directory) plus `--app-dir backend`. The container will need the equivalent.

---

## Step 5: Where this lands in Docker Compose (final phase, not built)

```mermaid
flowchart LR
    FE["frontend :3000"] -->|"/api/v1"| BE["backend :8000<br/>app + rag"]
    BE --> PG[("Postgres / Supabase")]
    BE --> RD[("redis :6379<br/>cache rag:*, rate limit")]
    BE -->|"QDRANT_URL"| QD[("qdrant :6333<br/>volume: qdrant_data")]
    BE -.->|"LLM_PROVIDER"| LLM["LLM API (external)"]
    classDef future stroke-dasharray: 5 5,fill:#eee,color:#666
```

| Setting | Offline demo | Compose / cloud |
|---|---|---|
| `VECTOR_STORE` | `memory` | `qdrant` |
| `QDRANT_URL` | empty | `http://qdrant:6333` (service name, not localhost) |
| `QDRANT_API_KEY` | empty | secret (Qdrant Cloud only), via the secrets manager |
| `QDRANT_COLLECTION` | `clouddesk_knowledge` | same |
| `REDIS_URL` | empty (fakeredis) | `redis://redis:6379/0` |
| `EMBEDDING_PROVIDER` / `EMBEDDING_DIMENSIONS` | `fake` / `384` | must match what built the collection |

**Dimension rule.** A Qdrant collection is created with a fixed vector size. Changing the embedding model changes the size, so the collection must be recreated: that is exactly what `POST /knowledge/reindex` does.

**Health.** `/health/ready` still reports the vector store as `ok` for `memory` and `error: not probed yet` for Qdrant. `QdrantVectorStore.health()` exists but is not yet called by readiness; wiring it is final-phase work.

---

## Status (honest)

| Item | State |
|---|---|
| Wiring inside one process (router → service → `rag/` → stores) | Implemented, validated locally |
| Redis cache for retrieval | Implemented with fakeredis; never run against real Redis |
| Qdrant store | Written, never run, dependency not installed |
| `make` targets | `make` is not installed on this Windows machine; the underlying commands were run directly |
| Dockerfile, Compose, Terraform, `rag/` in the image | Not built |
| Replica behaviour of the in-memory index | Reasoned, not tested |
| Cloud | Nothing deployed |
