# Phase 6: Infrastructure Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 6: Tools and policy.** This file explains how the tool layer is **wired** into the running application, what it talks to, how a call is routed, and what it means for Docker and the cloud in the final phase.

---

## Read this first: Phase 6 still has no Docker containers

There is no Dockerfile, Compose file or Terraform yet. The backend is one process on the developer's machine. Phase 6 adds **no new container, port, route, or environment variable**. The tool layer is plain Python inside the same process. It matters for infrastructure because it fixes *what the deployed backend will call outward to*.

| Decision in Phase 6 | Built? | Why Docker/cloud cares later |
|---|---|---|
| New `integrations/` package at the repo root | Built | Like `rag/`, the backend image must copy it and have the repo root on `PYTHONPATH` |
| `backend/app/tools/` package | Built | Inside `backend/`, nothing special |
| No new HTTP route | True | Same port 8000, same load-balancer rule `/api/v1/*` |
| Mock integrations (billing, email, notify, workspace admin) | Built | In-process, no network. Real adapters would need **egress** to those providers and **secrets** (Secrets Manager / Key Vault / Secret Manager) |
| `TOOL_TIMEOUT_SECONDS` | Already in settings | Must stay **below** the load balancer and probe timeouts |
| `APPROVAL_REQUIRED_FOR_REFUNDS`, `MAX_REFUND_WITHOUT_APPROVAL` | Already in settings | Policy knobs; must be set explicitly per environment (prod stays gated) |
| Tools reach the DB through `tool_session()` | Built | Uses the same `DATABASE_URL` pool as the API |
| `search_docs` uses the vector store and Redis cache | Built | Same `VECTOR_STORE`, `QDRANT_*`, `REDIS_URL` wiring as Phase 5 |
| Containers, network, volumes | **Not built** | Final phase |

---

## Step 1: Component wiring inside the process

```mermaid
flowchart LR
    subgraph Proc["One Python process (uvicorn, :8000)"]
        direction TB
        WF["Workflow nodes<br/>(Phases 9-10, not built)"] --> REG["ToolRegistry"]
        REG --> POL["ToolPolicy"]
        POL --> SET["get_settings()<br/>approval + timeout"]
        REG --> TOOLS["9 tools"]
        TOOLS --> SESS["tool_session()"]
        SESS --> ENG["SQLAlchemy engine"]
        TOOLS --> RET["rag.retriever"]
        TOOLS --> FAC["integrations.factory"]
        FAC --> MOCK["Mock adapters"]
    end
    ENG --> DB[("SQLite file<br/>→ Postgres in cloud")]
    RET --> VS["Vector store<br/>memory → Qdrant"]
    RET --> RD["Redis cache<br/>fakeredis → Redis"]
    MOCK -. "swap for real adapters" .-> EXT["Billing / email / chat APIs<br/>(external, not built)"]
```

Every arrow inside the box is a Python function call. Every arrow leaving the box is a network hop in the cloud version.

---

## Step 2: Routing of one tool call

The routing here is **in-process control flow**, not network routing. This is the path of `create_refund_request`.

```mermaid
sequenceDiagram
    participant C as Caller (workflow, later)
    participant R as ToolRegistry
    participant P as ToolPolicy
    participant T as create_refund_request
    participant S as tool_session / DB
    participant B as Billing adapter (mock)

    C->>R: execute("create_refund_request", args, approved=False)
    R->>P: requires_approval(name, args)
    P-->>R: True
    R-->>C: ToolResult(approval_required), nothing ran

    Note over C: A human approves (Phase 10)

    C->>R: execute("create_refund_request", args, approved=True)
    R->>P: requires_approval
    P-->>R: True (approved flag satisfies it)
    R->>T: ainvoke(args) inside wait_for(timeout)
    T->>S: read subscription (currency)
    T->>B: create_refund(...)
    B-->>T: {refund_id, status}
    T-->>R: data
    R-->>C: ToolResult(ok, executed=True)
```

A read tool skips the first half: the policy answers "no", and the call runs straight away.

---

## Step 3: Failure routing

```mermaid
flowchart TD
    A["execute()"] --> B{"approval needed<br/>and not given?"}
    B -->|"yes"| X1["approval_required"]
    B -->|"no"| C{"tool known?"}
    C -->|"no"| X2["unknown_tool"]
    C -->|"yes"| D["wait_for(tool, TOOL_TIMEOUT_SECONDS)"]
    D -->|"TimeoutError"| X3["timeout"]
    D -->|"any Exception"| X4["error"]
    D -->|"returns"| X5["ok"]
```

All five outcomes are a `ToolResult`. In the cloud this means a failing downstream provider produces a recorded result, never a crashed container and never a failed health probe.

---

## Step 4: Where the database session comes from

Tools do not receive a session from FastAPI, because they will be called from background workflow tasks, not from a request. Each tool opens its own short unit of work.

```mermaid
flowchart LR
    TOOL["tool function"] --> TS["tool_session()<br/>app/tools/base.py"]
    TS --> SS["database.session_scope()<br/>commit on success, rollback on error"]
    SS --> POOL["Engine pool per DATABASE_URL"]
    TEST["Tests"] -. "monkeypatch to a private<br/>in-memory DB" .-> TS
```

One seam, so tests never touch the real database. In production it is the same pool the API uses, so connection limits must cover API requests plus concurrent workflow tools.

---

## Step 5: Where this lands in Docker Compose (final phase, not built)

```mermaid
flowchart LR
    FE["frontend :3000"] -->|"REST /api/v1"| BE["backend :8000<br/>API + tools + workflow"]
    BE --> RD[("redis")]
    BE --> QD[("qdrant")]
    BE -->|"DATABASE_URL"| PG[("Postgres / Supabase")]
    BE -. "egress, secrets via env" .-> EXT["Billing / email / chat<br/>(future real adapters)"]
```

What the final phase must remember because of Phase 6:

1. The backend image copies `backend/`, `rag/` **and** `integrations/`.
2. Real adapters need outbound network access and secrets injected as `TF_VAR_*` / secret-manager values, never baked in the image.
3. `TOOL_TIMEOUT_SECONDS` must be shorter than the load balancer idle timeout.
4. Tools run in the backend container; there is no separate "tool service" in v1. A worker split later would still call the same registry.
5. Production must keep `APPROVAL_REQUIRED_FOR_REFUNDS=true`. A test in the delivery phase can assert the `.env.example` default.

---

## Status (honest)

| Item | State |
|---|---|
| Tool layer wired in-process | Implemented |
| Validated offline with a private SQLite database and mocks | Validated locally |
| Docker, Compose, Terraform | Not built |
| Real outbound integrations, egress rules, secrets | Not built, needs cloud credentials |
| Nothing is deployed | True |
