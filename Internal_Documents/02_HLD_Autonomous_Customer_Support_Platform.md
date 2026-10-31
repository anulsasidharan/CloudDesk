# High-Level Design (HLD)
## Autonomous Customer Support & Resolution Platform (ACSRP)

| Field | Value |
|---|---|
| Version | 1.0 (Draft) |
| Date | 31 October 2026 |
| Owner | Anu — OrionVexa |
| Inputs | `01_PRD_BRD_Autonomous_Customer_Support_Platform.md` |
| Next | `03_LLD_Autonomous_Customer_Support_Platform.md` |

---

## 1. Architecture Goals

| Goal | Design response |
|---|---|
| Act, not just answer | Agents call governed tools via MCP; policy engine + HITL decides what runs |
| Safe autonomy | Risk tiers, approval interrupts, guardrails at input/output/action layers |
| Grounded answers | Hybrid retrieval + reranking + citation-enforced generation |
| Durable long-running workflows | LangGraph with Postgres checkpointer; background workers |
| Cloud portability | Containers + Terraform; cloud specifics behind adapter interfaces |
| Observable & evaluable | OpenTelemetry + LLM tracing + eval pipeline wired into CI |
| Cost aware | Model routing, caching, token budgets |

---

## 2. System Context

```mermaid
flowchart LR
    C[Customer] -->|Chat widget / Email / App| ACSRP
    A[Support Agent / Supervisor / Admin] -->|Dashboard| ACSRP
    subgraph ACSRP[Autonomous Customer Support & Resolution Platform]
    end
    ACSRP -->|LLM / Embeddings / Rerank| LLM[(LLM Providers via Gateway)]
    ACSRP -->|MCP tools| BO[Back-office systems<br/>CRM · Billing · Orders · Status · Ticketing]
    ACSRP -->|OIDC| IDP[Identity Provider]
    ACSRP -->|Email out| MAIL[Email Service]
    ACSRP -->|Traces, metrics, logs| OBS[Observability stack]
```

---

## 3. Logical Architecture

```mermaid
flowchart TB
    subgraph Edge
        WAF[WAF / CDN] --> GW[API Gateway / Ingress<br/>TLS · Auth · Rate limit]
    end

    subgraph Frontend
        WEB[Next.js Dashboard]
        WID[Embeddable Chat Widget]
    end

    subgraph Core["Backend (FastAPI)"]
        API[Support API<br/>tickets · messages · approvals · admin]
        RT[Realtime Gateway<br/>WebSocket / SSE]
        CH[Channel Adapters<br/>email · webhook · ticketing]
    end

    subgraph AgentRuntime["Agent Runtime (LangGraph)"]
        SUP[Support Supervisor Agent]
        CUS[Customer Agent]
        KNO[Knowledge / RAG Agent]
        TRB[Troubleshooting Agent]
        RES[Resolution Agent]
        ESC[Escalation Agent]
        GR[Guardrails Service]
        POL[Policy Engine]
    end

    subgraph Tools["MCP Tool Servers"]
        M1[crm-mcp]
        M2[billing-mcp]
        M3[orders-mcp]
        M4[ticketing-mcp]
        M5[status-mcp]
        M6[knowledge-mcp]
    end

    subgraph Workers["Background Workers"]
        ING[Ingestion & Indexing]
        SUMW[Summaries & Resolution Cards]
        EVW[Evaluation jobs]
        NOT[Notifications / SLA timers]
    end

    subgraph Data
        PG[(PostgreSQL<br/>OLTP + checkpoints + audit)]
        RD[(Redis<br/>cache · sessions · rate limit · queue)]
        VDB[(Vector DB<br/>docs · tickets · memory)]
        OBJ[(Object Storage<br/>raw docs · attachments)]
    end

    LLMG[LLM Gateway<br/>routing · failover · cost]

    WEB --> GW
    WID --> GW
    GW --> API
    GW --> RT
    CH --> API
    API --> SUP
    SUP --> CUS & KNO & TRB & RES & ESC
    CUS & TRB & RES --> Tools
    KNO --> VDB
    KNO --> M6
    RES --> POL
    SUP --> GR
    AgentRuntime --> LLMG
    API --> PG
    API --> RD
    AgentRuntime --> PG
    AgentRuntime --> RD
    ING --> OBJ
    ING --> VDB
    Workers --> RD
    Workers --> PG
```

### 3.1 Component Responsibilities

| Component | Responsibility | Tech |
|---|---|---|
| Next.js Dashboard | Inbox, ticket view, approvals, escalations, analytics, admin | Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Chat Widget | Customer chat, streaming replies, attachments | React web component, SSE/WebSocket |
| API Gateway / Ingress | TLS, JWT validation, coarse rate limits, routing | Cloud API gateway / NGINX ingress |
| Support API | REST endpoints, validation, RBAC, orchestration trigger | FastAPI, Pydantic v2, SQLAlchemy 2 (async) |
| Realtime Gateway | Push ticket/agent events to UI | FastAPI WebSockets + Redis Pub/Sub |
| Channel Adapters | Normalise email/webhook/ticketing input | FastAPI routers + workers |
| Agent Runtime | Multi-agent graph execution, checkpoints, interrupts | LangGraph, LangChain core |
| Guardrails Service | Input/output checks (injection, PII, toxicity, groundedness) | Python module + small LLM + Presidio |
| Policy Engine | Risk-tier decisions for actions | Rules in YAML/OPA-style evaluator |
| MCP Tool Servers | Typed, permissioned access to back-office systems | MCP Python SDK (streamable HTTP) |
| LLM Gateway | Provider abstraction, routing, retries, failover, cost tracking | LiteLLM (or VexaRoute) |
| Background Workers | Ingestion, indexing, summaries, evals, SLA timers | Celery / arq on Redis |
| PostgreSQL | System of record, LangGraph checkpoints, audit, BM25 (optional) | PostgreSQL 16 (+ pgvector option) |
| Redis | Cache, sessions, rate limiting, queues, short-term memory | Redis 7 |
| Vector DB | Dense vectors for docs, tickets, resolution cards, memory | Qdrant (default) — pgvector as low-ops option |
| Object Storage | Raw documents, attachments, exports | S3 / Blob / GCS |

---

## 4. Multi-Agent Architecture

### 4.1 Pattern
**Supervisor (hierarchical) graph** with specialist agents as sub-graphs. The supervisor owns the ticket state and routes; specialists return structured results. Shared state is a typed `TicketState`.

```mermaid
flowchart TD
    START((New message)) --> IG[Input Guardrails]
    IG -->|blocked| SAFE[Safe reply / handoff]
    IG --> SUP{Support Supervisor}
    SUP -->|need customer context| CUS[Customer Agent]
    SUP -->|need knowledge| KNO[Knowledge / RAG Agent]
    SUP -->|need diagnosis| TRB[Troubleshooting Agent]
    SUP -->|ready to resolve| RES[Resolution Agent]
    SUP -->|risk / low confidence| ESC[Escalation Agent]
    CUS --> SUP
    KNO --> SUP
    TRB --> SUP
    RES --> POL{Policy Engine}
    POL -->|low risk| EXE[Execute via MCP]
    POL -->|medium/high| HITL[[Interrupt: Human approval]]
    POL -->|prohibited| ESC
    HITL -->|approved| EXE
    HITL -->|rejected| SUP
    EXE --> VER[Verify outcome]
    VER --> OG[Output Guardrails]
    OG --> REPLY[Reply to customer]
    ESC --> HANDOFF[Case brief + queue routing]
    REPLY --> MEM[Update memory + summary]
    HANDOFF --> MEM
    MEM --> END((End / await next message))
```

### 4.2 Agent Responsibilities

| Agent | Purpose | Inputs | Outputs | Tools |
|---|---|---|---|---|
| **Support Supervisor** | Understand, classify, plan route, decide when done | Message, ticket state | `Triage` (intent, category, severity, sentiment, entities), next route | None (LLM only) |
| **Customer Agent** | Build customer context | Customer ID / email | `CustomerContext` (profile, plan, orders, invoices, open tickets, memory) | crm, billing, orders, ticketing, memory |
| **Knowledge / RAG Agent** | Retrieve grounded evidence | Query, triage, context | `EvidencePack` (chunks, scores, citations, sufficiency) | knowledge-mcp, vector DB |
| **Troubleshooting Agent** | Hypothesise and diagnose | Triage, evidence, context | `Diagnosis` (hypotheses, checks, findings, root cause, confidence) | status, orders, crm (read-only diagnostics) |
| **Resolution Agent** | Plan resolution, draft reply, request actions | Diagnosis, evidence, policy | `ResolutionPlan` (steps, actions, risk, reply draft) | Write tools (via policy) |
| **Escalation Agent** | Hand off safely | Full state, reason | `EscalationBrief` (summary, evidence, owner queue, urgency) | ticketing, notifications |

### 4.3 Routing Rules (Supervisor)
1. Always run Customer Agent first if customer is identified and context is stale (> 5 min).
2. P1, security, legal, fraud, self-harm, or explicit "talk to a human" → Escalation directly.
3. Informational intent → Knowledge → Resolution (reply only).
4. Problem intent → Knowledge + Troubleshooting (parallel fan-out) → Resolution.
5. Confidence < 0.6 after 2 investigation cycles or `max_steps` reached → Escalation.

---

## 5. Knowledge & Retrieval Design

### 5.1 Ingestion Pipeline
```mermaid
flowchart LR
    SRC[Sources: PDF · MD · HTML · URLs · resolved tickets] --> LOAD[Load & parse]
    LOAD --> CLEAN[Clean · dedupe · PII scrub]
    CLEAN --> CHUNK[Structure-aware chunking<br/>headings · 400–800 tokens · overlap]
    CHUNK --> ENRICH[Enrich: title, product, version, section path, summary, keywords]
    ENRICH --> EMB[Embed]
    ENRICH --> SPARSE[Sparse / BM25 index]
    EMB --> VDB[(Vector DB)]
    SPARSE --> VDB
    ENRICH --> PG[(Postgres metadata)]
```

### 5.2 Retrieval Pipeline (Advanced + Agentic RAG)
```mermaid
flowchart LR
    Q[Query + triage] --> RW[Query rewrite / decomposition<br/>+ HyDE optional]
    RW --> F[Metadata filters<br/>tenant · product · version]
    F --> D[Dense search k=40]
    F --> S[Sparse BM25 k=40]
    D --> RRF[Reciprocal Rank Fusion]
    S --> RRF
    RRF --> RR[Cross-encoder rerank → top 8]
    RR --> SC{Sufficiency check}
    SC -->|insufficient| RW
    SC -->|sufficient| EP[Evidence Pack + citations]
```

Collections: `kb_docs`, `resolved_tickets`, `resolution_cards`, `customer_memory` (per-tenant payload filtering).

---

## 6. Memory Architecture

| Layer | Scope | Store | TTL | Contents |
|---|---|---|---|---|
| Working memory | One graph run | LangGraph state | Run | Messages, triage, evidence, plan |
| Conversation memory | Ticket thread | Postgres checkpoints + Redis cache | Ticket lifetime | Full thread, summarised beyond N turns |
| Customer long-term memory | Customer | Postgres (facts) + Vector DB (semantic) | Until erased | Preferences, environment, past issues, commitments |
| Organisational memory | Tenant | Vector DB (`resolution_cards`) | Versioned | Distilled successful resolutions |

Memory writes happen at the end of a run via a **memory extraction step** with structured output and confidence; low-confidence facts are discarded.

---

## 7. Human-in-the-Loop & Policy

- Resolution Agent emits proposed `ActionRequest`s; nothing executes directly from the LLM.
- Policy Engine evaluates `(tenant, action, args, customer tier, amount, history)` → `low | medium | high | prohibited`.
- Medium/high → LangGraph `interrupt()`; state persisted; `approval_requests` row created; dashboard notified.
- Approver decision resumes the graph via `Command(resume=...)`.
- Timeouts → auto-escalate; all decisions written to `audit_log`.

---

## 8. Integration via MCP

```mermaid
flowchart LR
    AR[Agent Runtime<br/>MCP client] -- streamable HTTP + service token --> REG[Tool Registry]
    REG --> CRM[crm-mcp]
    REG --> BIL[billing-mcp]
    REG --> ORD[orders-mcp]
    REG --> TKT[ticketing-mcp]
    REG --> STA[status-mcp]
    REG --> KN[knowledge-mcp]
    CRM & BIL & ORD & TKT & STA --> BO[(Sandbox back-office services / mocks)]
```

- Each MCP server declares tools with JSON schemas, a `risk_tier` default and `read_only` flag.
- Per-agent allow-lists: only Resolution Agent may call write tools.
- Service-to-service auth: short-lived JWT (client credentials) + mTLS within cluster.

---

## 9. Key Sequence — Chat Message to Resolution

```mermaid
sequenceDiagram
    autonumber
    participant W as Chat Widget
    participant API as FastAPI
    participant Q as Redis Queue
    participant G as LangGraph Runtime
    participant L as LLM Gateway
    participant M as MCP Servers
    participant DB as Postgres
    participant UI as Dashboard

    W->>API: POST /v1/conversations/{id}/messages
    API->>DB: persist message, upsert ticket
    API->>Q: enqueue run(ticket_id)
    API-->>W: 202 + stream URL
    Q->>G: start/resume thread(ticket_id)
    G->>L: guardrails + triage
    G->>M: customer context (read)
    G->>G: fan-out Knowledge + Troubleshooting
    G->>L: resolution plan (structured)
    alt low risk
        G->>M: execute action (idempotency key)
    else needs approval
        G->>DB: approval_request, checkpoint
        G-->>UI: approval.pending event
        UI->>API: POST /approvals/{id}/decision
        API->>G: resume(Command)
        G->>M: execute action
    end
    G->>L: output guardrails
    G-->>W: stream reply (SSE)
    G->>DB: summary, memory, audit, metrics
```

---

## 10. Security Architecture

| Layer | Control |
|---|---|
| Identity | OIDC (Auth0/Keycloak/Entra ID/Cognito/Identity Platform); JWT access tokens; customers via widget session token |
| Authorisation | RBAC: `customer`, `agent`, `supervisor`, `admin`, `platform_engineer`, `service`; tenant scoping on every query (row-level security) |
| API security | Input validation (Pydantic), CORS allow-list, CSRF for cookie flows, request size limits, OWASP API Top 10 |
| Rate limiting | Edge (gateway) + app-level token-bucket in Redis per tenant/user/IP; LLM token budgets |
| Secrets | AWS Secrets Manager / Azure Key Vault / GCP Secret Manager via workload identity |
| Data | TLS everywhere, encryption at rest (KMS), PII redaction in logs/traces |
| AI security | Injection classifier, content isolation (untrusted text never treated as instructions), tool allow-lists, arg validation, policy engine |
| Supply chain | Image scanning (Trivy), SBOM, dependency pinning, signed images |
| Audit | Append-only audit log for decisions, actions, approvals, admin changes |

---

## 11. Observability & Evaluation

```mermaid
flowchart LR
    APP[API · Agents · Workers · MCP] -- OTel traces/metrics/logs --> COL[OTel Collector]
    APP -- LLM spans --> LF[Langfuse / LangSmith]
    COL --> TR[Traces: Tempo/X-Ray/App Insights/Cloud Trace]
    COL --> ME[Metrics: Prometheus → Grafana]
    COL --> LO[Logs: Loki / CloudWatch / Log Analytics / Cloud Logging]
    LF --> EV[Eval pipeline]
    EV --> GATE[CI release gate]
```

- Correlation: `ticket_id`, `run_id`, `trace_id` on every log line and span.
- Golden signals + AI signals: autonomous rate, escalation rate, groundedness, tool error rate, tokens/cost per ticket, approval latency.
- Offline evals (golden dataset) in CI; online evals sample 5–10% of traffic with LLM-as-judge + human QA.

---

## 12. Deployment Architecture

### 12.1 Runtime Topology (per cloud)
```mermaid
flowchart TB
    U[Users] --> CDN[CDN + WAF]
    CDN --> LB[Load Balancer / Ingress]
    subgraph K8s["Kubernetes cluster (private subnets)"]
        FE[web: Next.js]
        BE[api: FastAPI]
        AG[agent-runtime]
        WK[workers]
        MCP[mcp-servers]
        OT[otel-collector]
    end
    LB --> FE
    LB --> BE
    BE --> AG
    AG --> MCP
    subgraph Managed["Managed services"]
        PG[(Managed PostgreSQL)]
        RD[(Managed Redis)]
        OB[(Object Storage)]
        SM[Secret Manager]
    end
    BE & AG & WK --> PG & RD
    WK --> OB
    AG --> VDB[(Qdrant on K8s / Qdrant Cloud)]
```

Deployment units are identical containers; Kubernetes is the default target for parity. A lighter "serverless containers" profile (ECS Fargate / Azure Container Apps / Cloud Run) is also defined.

### 12.2 Cloud Service Mapping

| Capability | AWS | Azure | GCP |
|---|---|---|---|
| Containers (K8s) | EKS | AKS | GKE |
| Containers (serverless) | ECS Fargate / App Runner | Azure Container Apps | Cloud Run |
| Container registry | ECR | ACR | Artifact Registry |
| PostgreSQL | RDS / Aurora PostgreSQL | Azure Database for PostgreSQL Flexible Server | Cloud SQL for PostgreSQL / AlloyDB |
| Redis | ElastiCache for Redis | Azure Cache for Redis / Azure Managed Redis | Memorystore for Redis |
| Vector DB | Qdrant on EKS · OpenSearch · pgvector | Qdrant on AKS · Azure AI Search · pgvector | Qdrant on GKE · Vertex AI Vector Search · pgvector |
| Object storage | S3 | Blob Storage | Cloud Storage |
| LLM (managed) | Bedrock | Azure OpenAI / AI Foundry | Vertex AI |
| Secrets | Secrets Manager | Key Vault | Secret Manager |
| Identity (workload) | IRSA / EKS Pod Identity | Workload Identity | Workload Identity |
| Identity (users) | Cognito | Entra ID | Identity Platform |
| API gateway / LB | API Gateway / ALB | API Management / App Gateway | API Gateway / Cloud Load Balancing |
| WAF / CDN | AWS WAF + CloudFront | Front Door + WAF | Cloud Armor + Cloud CDN |
| Queue (optional) | SQS | Service Bus | Pub/Sub |
| Email | SES | Azure Communication Services | SendGrid (marketplace) |
| Logs / metrics | CloudWatch | Azure Monitor / Log Analytics | Cloud Logging / Monitoring |
| Tracing | X-Ray (via OTel) | Application Insights | Cloud Trace |
| IaC state | S3 + DynamoDB lock | Storage Account | GCS bucket |
| DNS / TLS | Route 53 + ACM | Azure DNS + Key Vault certs | Cloud DNS + Certificate Manager |

### 12.3 Environments
`local` (Docker Compose) → `dev` → `staging` → `prod` per cloud. Promotion by Git tag; same image digest across clouds.

### 12.4 CI/CD
```mermaid
flowchart LR
    PR[Pull request] --> LINT[Lint · type-check · unit tests]
    LINT --> INT[Integration tests<br/>Compose services]
    INT --> EVAL[Agent & RAG eval gate]
    EVAL --> SEC[SAST · dep scan · image scan]
    SEC --> BUILD[Build & sign images]
    BUILD --> PUSH[Push to ECR · ACR · Artifact Registry]
    PUSH --> TF[Terraform plan/apply per cloud]
    TF --> DEP[Helm deploy → dev]
    DEP --> SMOKE[Smoke + synthetic tickets]
    SMOKE --> PROMO[Manual approval → staging → prod]
```

---

## 13. Scalability & Resilience

| Concern | Approach |
|---|---|
| Burst traffic | API stateless, HPA on CPU/RPS; agent runs queued in Redis; workers scale on queue depth (KEDA) |
| Long-running runs | Checkpointed graphs; resumable after pod restarts |
| LLM latency | Streaming, parallel fan-out, small models for triage, semantic cache for FAQs |
| Provider failure | Gateway failover chain; circuit breaker; degrade to human handoff |
| DB load | Read replicas for analytics; connection pooling (PgBouncer) |
| Vector DB | Sharded/replicated collections; payload index on `tenant_id` |
| DR | PITR backups for Postgres; vector index rebuildable from Postgres + object storage; RPO 15 min / RTO 1 h |

---

## 14. Key Architecture Decisions (summary)

| ADR | Decision | Rationale |
|---|---|---|
| ADR-01 | LangGraph supervisor pattern | Explicit control flow, checkpoints, interrupts for HITL |
| ADR-02 | MCP for all tool access | Standard, typed, permissioned; reusable across agents/apps |
| ADR-03 | Qdrant default, pgvector option | Native hybrid (dense+sparse), payload filters; pgvector for minimal ops |
| ADR-04 | Postgres as checkpointer and audit store | One durable system of record |
| ADR-05 | LLM gateway in front of providers | Multi-cloud model portability, failover, cost tracking |
| ADR-06 | Kubernetes as parity target | Same Helm chart on EKS/AKS/GKE |
| ADR-07 | Policy engine outside the LLM | Deterministic, auditable risk decisions |
| ADR-08 | Redis queue for runs (cloud queues optional) | Portable; same behaviour on all clouds |
