# Phase 1: Infrastructure Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 1: Runtime skeleton.** This file explains how the parts of the application are **connected**: which process runs, on which port, how a request is routed inside it, how the server decides which database, cache or AI to use, and how health monitors talk to it.

---

## Read this first: Phase 1 has no Docker containers yet

Phase 1 does **not** contain Dockerfiles, Docker Compose or cloud (Terraform) files. Those are built in the final delivery phase. In Phase 1 the whole backend runs as **one program on the developer's computer**.

Phase 1 still makes almost every wiring decision that the containers will later rely on:

| Decision made in Phase 1 | Why Docker and the cloud need it later |
|---|---|
| Backend listens on port **8000** | The container exposes the same port; the load balancer forwards to it |
| All settings come from **environment variables** | Containers and cloud services inject settings the same way, with no code change |
| `/health/live` touches nothing | Docker `HEALTHCHECK` and cloud liveness probes call it |
| `/health/ready` returns **503** when degraded | Load balancers stop sending traffic to an unready container |
| CORS allows the console origin (port **3000**) | The frontend container calls the backend container across origins |
| Every response carries `X-Request-ID` | A request can be traced through the load balancer, the container and the logs |
| Logs go to **standard output** as JSON | `docker logs`, CloudWatch, Log Analytics and Cloud Logging collect stdout |
| Offline stand-ins exist for every store | Tests and demos need no containers at all |

**Diagram key:** solid boxes exist in that step. Dashed grey boxes are planned for later phases and appear only to show where they will connect.

---

## Step 0: Where the infrastructure is headed

### Target: local Docker Compose network (final delivery phase)

The finished application will run as four containers on one private Docker network. Only the frontend and the backend are reachable from the developer's browser. Redis and Qdrant are reachable only by the backend, using their service names as hostnames.

```mermaid
flowchart LR
    BR["Browser"] -->|"http://localhost:3000"| FE
    BR -->|"http://localhost:8000<br/>REST /api/v1"| BE

    subgraph NET["Docker Compose network (planned)"]
        FE["frontend<br/>Next.js · :3000"]
        BE["backend<br/>FastAPI · :8000"]
        RD["redis<br/>:6379"]
        QD["qdrant<br/>vector DB"]
        BE -->|"redis://redis:6379/0"| RD
        BE -->|"QDRANT_URL"| QD
    end

    BE --> VOL[("named volumes<br/>data/support.db,<br/>checkpoints.db")]
    QD --> VOL
    BE -->|"HTTPS"| LLM["LLM API<br/>(external)"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class FE,BE,RD,QD,VOL,LLM future
```

Compose start-up order is `frontend → backend → redis, qdrant`. Each container waits until the one it depends on reports **healthy** (`depends_on: service_healthy`). That health signal is the `/health/live` route built in Phase 1.

### Target: cloud deployment (final delivery phase)

```mermaid
flowchart LR
    U["Support agents"] -->|HTTPS| LB["Load balancer<br/>AWS ALB · Azure / GCP ingress"]
    subgraph CLOUD["Cloud account (planned)"]
        LB --> WEB["frontend container"]
        LB --> API["backend container(s)"]
        API --> CACHE["Managed Redis"]
        API --> SEC["Secrets manager"]
        API --> MONI["Log + monitoring<br/>CloudWatch / Log Analytics /<br/>Cloud Logging"]
    end
    API --> SUPA["Supabase Postgres<br/>(external)"]
    API --> QC["Qdrant Cloud<br/>(external)"]
    API --> LLM["LLM API<br/>(external)"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class LB,WEB,API,CACHE,SEC,MONI,SUPA,QC,LLM future
```

### What existed at the start of Phase 1

No running process, no ports and no network. Only the plans above.

---

## Step 1: P1-1, settings and logging (the wiring switchboard)

### What was added

The **settings panel** (`backend/app/core/config.py`) acts as the system's switchboard. Each environment variable decides which real or stand-in component a part of the system is connected to. The code never hard-codes an address. It asks the settings panel.

```mermaid
flowchart LR
    subgraph SRC["Where settings come from (highest wins)"]
        OS["Environment variables<br/>(container / cloud / test harness)"]
        DOT[".env file<br/>(local developer only)"]
        DEF["Built-in defaults<br/>(offline demo)"]
    end
    OS --> CFG
    DOT --> CFG
    DEF --> CFG
    CFG["Settings panel<br/>get_settings(), cached per process"]

    CFG --> SW1{"DATABASE_URL"}
    SW1 -->|"sqlite+aiosqlite:///./data/support.db<br/>(default)"| DB1["Local SQLite file"]
    SW1 -.->|"postgresql+asyncpg://..."| DB2["Postgres / Supabase"]

    CFG --> SW2{"REDIS_URL"}
    SW2 -->|"empty (default)"| R1["fakeredis<br/>in-process"]
    SW2 -.->|"redis://redis:6379/0"| R2["Redis container"]

    CFG --> SW3{"VECTOR_STORE"}
    SW3 -->|"memory (default)"| V1["In-memory store"]
    SW3 -.->|"qdrant + QDRANT_URL"| V2["Qdrant"]

    CFG --> SW4{"LLM_PROVIDER"}
    SW4 -->|"fake (default)"| L1["Fake LLM, offline"]
    SW4 -.->|"openai / anthropic / ..."| L2["Real LLM API"]

    CFG --> SW5{"CORS_ORIGINS"}
    SW5 -->|"http://localhost:3000"| C1["Allowed browser origin"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class DB2,R2,V2,L2 future
```

**Plain words:** one environment variable decides whether the system uses a pretend component on the laptop or a real server. Phase 1 wires up the **switches**. The real connections are built in later phases. Defaults always choose the offline option, so the system runs anywhere with nothing installed.

### Logging wiring

```mermaid
flowchart LR
    APP["Any part of the backend"] --> LOG["JSON logbook<br/>core/logging.py"]
    LOG --> STDOUT["Standard output<br/>one JSON object per line"]
    STDOUT --> TERM["Phase 1: developer's terminal"]
    STDOUT -.-> DL["Later: docker logs"]
    STDOUT -.-> CL["Later: CloudWatch /<br/>Log Analytics /<br/>Cloud Logging"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class DL,CL future
```

Logs are written to standard output, never to a file inside the app. This is the standard container practice: the platform collects stdout, and the app never has to know where logs end up.

### Security of the wiring

Addresses such as `DATABASE_URL` and `REDIS_URL` can contain passwords. The settings panel masks them (`postgresql://***@host/db`) whenever settings are printed. API keys are stored as a protected type that shows `**********`. In the cloud phase, real values come from a secrets manager as environment variables. The code path stays the same.

---

## Step 2: P1-2, the server process, ports and request routing

### What was added

A real **network listener**. The backend now runs as a web server on port 8000 and routes incoming requests through checkpoints to the right handler.

### The process on the developer machine

```mermaid
flowchart TB
    subgraph HOST["Developer computer (Windows)"]
        subgraph PROC["One Python process"]
            UV["Uvicorn<br/>ASGI web server<br/>listens on 127.0.0.1:8000"]
            APP["FastAPI app<br/>app.main:app"]
            UV --> APP
            APP --> INPROC["In-process stand-ins<br/>fakeredis · in-memory vectors ·<br/>fake LLM"]
        end
        FILE[("./data/support.db<br/>SQLite file (configured,<br/>opened from Phase 2)")]
        APP -.-> FILE
    end
    BROWSER["Browser / curl /<br/>health monitor"] -->|"HTTP :8000"| UV
```

**Uvicorn** is the program that actually opens port 8000 and speaks HTTP. It hands each request to the **FastAPI app**, which decides what to do with it. In a container, Uvicorn listens on `0.0.0.0:8000` instead of `127.0.0.1`, so the Docker network can reach it.

### How one request is routed inside the server

```mermaid
flowchart TB
    IN["HTTP request arrives on :8000"] --> UV["Uvicorn<br/>turns raw HTTP into an ASGI call"]
    UV --> CORS
    subgraph STACK["Middleware stack (outermost first)"]
        CORS["1. CORS<br/>is the browser origin allowed?<br/>answers OPTIONS pre-flight"]
        RID["2. Request ID<br/>keep safe X-Request-ID or create UUID,<br/>bind it to the logs"]
        RL["3. Rate limit<br/>Phase 3"]
        AU["4. Audit<br/>Phase 3"]
        CORS --> RID
        RID -.-> RL -.-> AU
    end
    RID --> RT
    AU -.-> RT
    RT{"Router<br/>match path"}
    RT -->|"/health"| H["Identity: name, version, env"]
    RT -->|"/health/live"| L["alive (no I/O)"]
    RT -->|"/health/ready"| R["readiness checks"]
    RT -.->|"/api/v1/..."| V1["Business API<br/>Phase 4 onward"]
    RT -->|"anything else"| NF["404 Not Found<br/>(still gets X-Request-ID)"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class RL,AU,V1 future
```

### Route table at the end of P1-2

| Path | Prefix | Purpose | Touches other systems? | Used by |
|---|---|---|---|---|
| `GET /health` | none | Service name, version, environment | No | Humans, dashboards |
| `GET /health/live` | none | "Process is up" | **No, by design** | Docker `HEALTHCHECK`, liveness probes |
| `GET /health/ready` | none | "Can serve traffic"; 503 when degraded | Reads settings only (no network calls yet) | Load balancers, readiness probes |
| `/api/v1/...` | `/api/v1` | All business routes | Yes | Frontend (Phase 4 onward) |

Health routes deliberately sit **outside** `/api/v1`. Probes then keep working even if API versioning changes, and they will not require a login once authentication arrives in Phase 3.

### Cross-origin wiring (frontend :3000 → backend :8000)

The console (frontend) and the backend run on different ports, so the browser treats them as different **origins**. CORS is the permission slip that lets the browser make the call and read the reply.

```mermaid
sequenceDiagram
    participant B as Browser (page from :3000)
    participant C as CORS middleware (:8000)
    participant R as Request ID middleware
    participant H as Route handler
    B->>C: OPTIONS pre-flight · Origin: http://localhost:3000
    C-->>B: 200 · Access-Control-Allow-Origin: http://localhost:3000
    B->>C: GET /health/ready
    C->>R: origin allowed
    R->>H: request + request_id
    H-->>R: JSON body
    R-->>C: add X-Request-ID header
    C-->>B: reply · Access-Control-Expose-Headers: X-Request-ID
    Note over B: Without "expose", browser code<br/>could not read the tracking number
```

### Request ID across the future network hops

The tracking number is designed to travel through every hop. If an upstream component (such as a load balancer) already set a safe `X-Request-ID`, the backend keeps it. Otherwise the backend creates one. Unsafe values are replaced so nobody can forge log lines.

```mermaid
flowchart LR
    BR["Browser"] -.->|"no ID"| LB["Load balancer<br/>(cloud phase)"]
    LB -.->|"X-Request-ID: abc"| BE["Backend :8000<br/>keeps 'abc' if safe"]
    BR -->|"Phase 1: direct call"| BE
    BE --> LOGS["Every log line:<br/>request_id = abc"]
    BE -->|"response header<br/>X-Request-ID: abc"| BR

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class LB future
```

### Health probes and who calls them

```mermaid
flowchart LR
    subgraph CALLERS["Probe callers"]
        DEV["Developer / curl<br/>(Phase 1)"]
        DH["Docker HEALTHCHECK<br/>(planned)"]
        CMP["Compose depends_on:<br/>service_healthy (planned)"]
        LBP["Load balancer target check<br/>(planned)"]
        K8["Liveness / readiness probes<br/>ECS · Container Apps · Cloud Run · k8s<br/>(planned)"]
    end
    DEV --> LIVE["/health/live"]
    DEV --> READY["/health/ready"]
    DH -.-> LIVE
    CMP -.-> LIVE
    K8 -.-> LIVE
    LBP -.-> READY
    K8 -.-> READY

    READY --> CHK["Checks: database · redis ·<br/>vector_store · llm"]
    CHK -->|"all offline-ready"| OK["200 ready"]
    CHK -->|"any remote not yet probed"| DG["503 degraded<br/>(no URLs or keys in the reason)"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class DH,CMP,LBP,K8 future
```

**Why there are two probes:**

- **Live** answers "should this container be restarted?" It must not depend on the database. Otherwise a short database outage would make the platform restart every backend container for no benefit.
- **Ready** answers "should this container receive traffic?" If a dependency is missing, the load balancer routes around the container instead of sending users errors.

In Phase 1, Ready reports `ok` for the offline stand-ins and `error` ("not probed yet") for any remote service. Real connection checks are added when each client exists in later phases.

### Crash safety on the wire

If a handler fails before sending a response, the Request ID middleware sends a clean `500 {"detail":"Internal Server Error"}`, still stamped with the `X-Request-ID`. Nothing internal (stack traces, file paths, settings) ever crosses the network. The full error is written to the logs under the same ID.

---

## Step 3: P1-3, offline test harness (no network at all)

### What was added

Tests run the real app **without opening any port**. The test client calls the ASGI app directly in memory.

```mermaid
flowchart LR
    subgraph PYTEST["pytest process"]
        ENV["conftest.py sets env vars FIRST<br/>DEMO_MODE=true · LLM_PROVIDER=fake ·<br/>VECTOR_STORE=memory · USE_FAKE_REDIS=true ·<br/>DATABASE_URL = temp SQLite ·<br/>CHECKPOINT_DB_PATH=:memory:"]
        ENV --> APP["FastAPI app<br/>(same code as production)"]
        TC["TestClient"] -->|"in-memory ASGI calls,<br/>no socket, no port"| APP
        APP --> FAKE["Fake / in-memory stand-ins"]
        APP --> TMP[("Temporary folder<br/>clouddesk-tests-*")]
    end
    NET["Internet / Docker / API keys"] -. "never used" .- PYTEST
```

**Why it matters for infrastructure:** CI pipelines (later phase) can run the full test suite on a plain build machine without starting containers, databases or paid services. The same middleware and routing are tested exactly as they run in production.

---

## Step 4: P1-4, Makefile and `.env.example` (how a developer starts the wiring)

### What was added

```mermaid
flowchart TB
    DEV["Developer"] --> SETUP["make setup"]
    SETUP --> SYNC["uv sync<br/>install Python deps into .venv"]
    SETUP --> COPY{".env exists?"}
    COPY -->|no| CP["copy .env.example to .env<br/>(placeholders only)"]
    COPY -->|yes| KEEP["keep the developer's .env"]

    DEV --> RUN["make backend"]
    RUN --> UVR["cd backend<br/>uvicorn app.main:app --reload --port 8000"]
    UVR --> PORT["Listening on :8000<br/>auto-restarts on code change"]

    DEV --> TEST["make test"] --> PT["pytest, offline (Step 3)"]
    DEV --> LINT["make lint"] --> RF["ruff"]

    CP --> CFGR["Settings panel reads .env at start-up"]
    KEEP --> CFGR
```

- **`.env.example`** is committed and lists every setting the system uses, with placeholder values. It is the single list of "wires" that a container or cloud service must provide.
- **`.env`** holds real local values and is git-ignored. It is never baked into a container image.
- On Windows without `make`, run the same commands directly with `.venv/Scripts/python.exe`. `PYTHONPATH` must include `backend`.

---

## Step 5: End of Phase 1, the complete wiring

### Everything that is connected at the end of Phase 1

```mermaid
flowchart TB
    subgraph CALLERS["Callers"]
        DEVB["Developer browser / curl"]
        TESTS["pytest TestClient<br/>(in-memory)"]
        FEB["Console :3000<br/>(Phase 12)"]
    end

    subgraph HOST["Developer computer"]
        subgraph PROC["Backend process · Uvicorn :8000"]
            CORS["CORS<br/>allow :3000,<br/>expose X-Request-ID"] --> RID["Request ID<br/>+ crash-safe 500"]
            RID --> ROUTER{"Router"}
            ROUTER --> H["/health"]
            ROUTER --> L["/health/live"]
            ROUTER --> R["/health/ready"]
            R --> RDY["Readiness checker"]
            H --> CFG
            RDY --> CFG["Settings switchboard"]
            RID --> LOG["JSON logbook"]
        end
        ENVF[".env"] --> CFG
        LOG --> OUT["stdout (terminal)"]
    end

    DEVB -->|"HTTP :8000"| CORS
    TESTS -->|"ASGI, no port"| CORS
    FEB -.-> CORS

    CFG -.->|"DATABASE_URL"| DB[("SQLite / Postgres<br/>Phase 2")]
    CFG -.->|"REDIS_URL"| RD[("Redis<br/>Phase 3 rate limit")]
    CFG -.->|"VECTOR_STORE"| VS[("Vector store<br/>Phase 5")]
    CFG -.->|"LLM_PROVIDER"| LLM["LLM<br/>Phase 8"]

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class FEB,DB,RD,VS,LLM future
```

### How Phase 1 maps onto the future Docker network

Each Phase 1 piece has a direct place in the planned containers. Nothing has to be redesigned.

```mermaid
flowchart LR
    subgraph P1["Built in Phase 1"]
        A1["Uvicorn on :8000"]
        A2["/health/live"]
        A3["/health/ready (503)"]
        A4["Env-var settings"]
        A5["JSON logs to stdout"]
        A6["CORS for :3000"]
        A7["X-Request-ID"]
    end
    subgraph FUT["Used by (planned)"]
        B1["backend container<br/>EXPOSE 8000"]
        B2["Dockerfile HEALTHCHECK +<br/>compose service_healthy"]
        B3["Load balancer target health"]
        B4["compose environment: /<br/>cloud secrets manager"]
        B5["docker logs / cloud logging"]
        B6["frontend container calls backend"]
        B7["trace across LB, container, logs"]
    end
    A1 --> B1
    A2 --> B2
    A3 --> B3
    A4 --> B4
    A5 --> B5
    A6 --> B6
    A7 --> B7

    classDef future fill:#f4f4f4,stroke:#999,stroke-dasharray: 5 5,color:#666;
    class B1,B2,B3,B4,B5,B6,B7 future
```

### Ports and addresses

| Component | Address in Phase 1 | Address planned in Docker Compose | Status |
|---|---|---|---|
| Backend API | `http://localhost:8000` | `backend:8000` (published to host :8000) | **Running in Phase 1** |
| Frontend console | (allowed by CORS only) | `frontend:3000` (published to host :3000) | Phase 12 |
| Database | `./data/support.db` (configured) | SQLite on a named volume, or external Supabase | Phase 2 |
| Redis | in-process fakeredis | `redis:6379`, internal only | Phase 3 onward |
| Vector store | in-process memory | `qdrant` service, internal only | Phase 5 |
| LLM | in-process fake | external HTTPS API | Phase 8 |

### Honest status

- **Implemented:** the process, port, routing, CORS, request ID, health probes, settings switchboard, offline harness and developer commands (P1-1 to P1-4).
- **Not in Phase 1:** Dockerfiles, Compose, Kubernetes, Terraform, CI pipelines, and any real connection to a database, Redis, Qdrant or an LLM. All of them are planned for later phases.
- **Known issue:** merge commit `2f297f5` left `backend/app/main.py` and `backend/app/middleware/request_id.py` with two versions mixed together, and neither file compiles. The server will not start until that merge is fixed. `pyproject.toml` also lists `fastapi`, `langchain`, `pydantic-settings` and `uvicorn` twice. The diagrams show the intended wiring.
- **Cloud:** no cloud credentials used; nothing deployed.
