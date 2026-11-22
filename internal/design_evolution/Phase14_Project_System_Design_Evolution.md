# Phase 14: System Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 14: Evaluation and delivery.** No product behaviour changes. The phase adds a **quality gate** around the system (evaluation thresholds) and a **delivery layer** (images, Compose, Terraform, CI, hygiene tests). `PLAN_PHASE.md` numbers this "Phase 13"; `TASKS.md`, which this build follows, calls it Phase 14.

---

## Step 0: Starting point (end of Phase 13)

A complete application that runs only as two local processes.

```mermaid
flowchart LR
    Agent(["Support agent"]) --> FE["Next.js console :3000"]
    FE -->|REST + Bearer JWT| API["FastAPI :8000"]
    API --> GR["LangGraph workflow + 6 agents"]
    API --> DB[("SQLite")]
    API --> RD[("fakeredis")]
    GR --> VS[("In-memory vector store")]
    GR --> LLM["Fake LLM provider"]
```

Quality was checked by scattered tests: classification and escalation had early bars (Phase 9), retrieval hit-rate lived under `tests/rag`. Nothing enforced citation or grounding, and nothing could be shipped.

---

## Step 1 (P14-1): Evaluation thresholds

One suite, `tests/evaluation/test_thresholds.py`, scores **all five** CLAUDE.md metrics over `datasets/eval_cases.json` (27 cases, all 13 demo tickets included). `tests/evaluation/conftest.py` re-exports the specialist harness so the exact pipeline the graph runs is scored.

```mermaid
flowchart TB
    DS[("datasets/eval_cases.json")] --> M1["Classification accuracy >= 0.80"]
    DS --> M2["Retrieval hit-rate@3 >= 0.75"]
    DS --> M3["Escalation correctness >= 0.90"]
    SD[("13 demo tickets")] --> P["Full specialist pipeline"]
    P --> M4["Citation rate >= 0.90"]
    P --> M5["Grounding rate >= 0.90"]
    M1 & M2 & M3 & M4 & M5 --> GATE{"All pass?"}
    GATE -->|no| RED["Build fails with the missed case ids"]
    GATE -->|yes| GREEN["Merge allowed"]
```

| Metric | Source of truth for "correct" |
|---|---|
| Classification | `expected_category` |
| Retrieval@3 | `expected_articles` titles, among the top 3 hits |
| Escalation | `expected_escalation` and `expected_team` must both match |
| Citation | every plan has citations and each starts with `kb://` |
| Grounding | every troubleshooting step text appears in the customer reply |

Failure messages list the **missed case ids**, so a regression is traceable in one read.

---

## Step 2 (P14-2): Backend and frontend images

```mermaid
flowchart LR
    subgraph Backend["backend/Dockerfile (context = repo root)"]
      B1["build stage: uv sync --frozen --no-dev"] --> B2["runtime stage python:3.12-slim, user app (uid 10001)"]
    end
    subgraph Frontend["frontend/Dockerfile (context = frontend/)"]
      F1["deps: npm ci"] --> F2["build: next build (standalone)"] --> F3["runtime node:22-alpine, user app"]
    end
    B2 -->|HEALTHCHECK| H1["/health/live"]
    F3 -->|HEALTHCHECK| H2["/api/health"]
```

Design choices: multi-stage so build tools never ship; non-root user; health checks use routes that do **no I/O** (`/health/live`); the frontend uses `output: "standalone"` and receives `NEXT_PUBLIC_API_URL` as a **build argument** because Next.js inlines it at build time.

---

## Step 3 (P14-3): Compose stack

```mermaid
flowchart TB
    FE["frontend :3000"] -->|depends_on healthy| BE["backend :8000"]
    BE -->|healthy| RD[("redis")]
    BE -->|healthy| QD[("qdrant")]
    RD --- V1[/"redis-data"/]
    QD --- V2[/"qdrant-data"/]
    BE --- V3[/"backend-data (SQLite + checkpoints)"/]
```

Start order is enforced by health, not by timing. The backend reads Redis at `redis://redis:6379/0` (service name inside the network). Qdrant is provisioned, but `VECTOR_STORE` stays `memory`; the app does not yet depend on it.

---

## Step 4 (P14-4): Terraform and CI scaffolds

```mermaid
flowchart LR
    subgraph IaC["deployment/"]
      AWS["aws: ECR, Secrets Manager, CloudWatch, ECS cluster"]
      AZ["azure: ACR, Log Analytics, resource group"]
      GC["gcp: Artifact Registry, Secret Manager"]
      K8["kubernetes: reference manifest"]
      SC["scripts: deploy, smoke_test"]
    end
    subgraph CI[".github/workflows"]
      T["test.yml"]; S["security.yml"]; D["docker-build.yml"]; V["terraform-validate.yml"]; DEP["_deploy.yml"]
    end
    T --> D --> DEP
    V --> DEP
    DEP -->|"prod only"| REV{{"Reviewer approval: prod-apply"}} --> APPLY["apply"] --> SMOKE["smoke test"]
```

Environments are **var-files**, not copies of code. Only `*.tfvars.example` is committed; real `terraform.tfvars`, `backend.hcl`, state and plans are git-ignored. Image tag = git SHA.

---

## Step 5 (P14-5): Deployment hygiene tests

`tests/deployment/test_deployment_hygiene.py` (19 tests) checks, with no Docker and no network:

```mermaid
flowchart LR
    T["19 static tests"] --> A["Dockerfiles: non-root USER, HEALTHCHECK, multi-stage"]
    T --> B["Compose: 4 services, healthy start order, restart policy, named volumes"]
    T --> C[".env.example lists every Settings field"]
    T --> D["No .env, tfvars, state or .db tracked by git"]
    T --> E["No key-shaped strings in delivery files"]
    T --> F["Each cloud has 3 env var-files; 5 workflows exist"]
    T --> G["deploy.sh refuses --auto-approve outside dev"]
```

The first run **failed** because the frontend Compose service lacked a health check. It was added, and the test now guards it.

---

## Final design at the end of Phase 14

```mermaid
flowchart TB
    Dev(["Developer"]) -->|push / PR| GH["GitHub Actions: test, security, docker-build, terraform-validate"]
    GH -->|"tested git SHA"| REG[("Container registry")]
    REG --> RUN["Cloud runtime (planned): ECS / Container Apps / Cloud Run"]
    subgraph Local["Local stack: docker compose up"]
      FE["frontend :3000"] --> BE["backend :8000"]
      BE --> RD[("redis")]
      BE --> QD[("qdrant (reserved)")]
      BE --> GR["LangGraph + agents + RAG"]
      GR --> LLM["LLM provider (fake by default)"]
    end
    EVAL["Evaluation gate: 5 thresholds"] -.->|blocks merge| GH
    HYG["Hygiene tests"] -.->|blocks merge| GH
```

### What Phase 14 does not change
No route, schema, migration, agent, rule or UI changed. The workflow still runs in-process.

### Known gaps (honest status)
| Item | State |
|---|---|
| Quality thresholds | Implemented, validated locally (432 tests pass) |
| `docker compose config -q` | Passes locally |
| Image builds, `docker compose up` | **Not run**: the Docker daemon was not running on the build machine |
| `terraform validate` | **Not run**: Terraform not installed; scaffolds are partial (no compute service, load balancer or Redis resources yet) |
| GitHub workflows | **Never executed** (not pushed with secrets) |
| Cloud deployment | **None**; no credentials used |
| Qdrant | Container defined; app code and the Qdrant client dependency are not wired |
| SQLite in a container | Single replica only until `DATABASE_URL` points at Postgres |
