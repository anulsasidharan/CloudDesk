# Product & Business Requirements Document (PRD / BRD)
## Autonomous Customer Support & Resolution Platform (ACSRP)

| Field | Value |
|---|---|
| Document type | PRD + BRD (combined) |
| Version | 1.0 (Draft) |
| Date | 31 October 2026 |
| Owner | Anu — OrionVexa (Agentic AI Production Engineering, Project 1) |
| Status | Draft for review |
| Related docs | `02_HLD_Autonomous_Customer_Support_Platform.md`, `03_LLD_Autonomous_Customer_Support_Platform.md` |

---

## 1. Executive Summary

Businesses receive support requests through email, live chat, ticketing systems and in-app widgets. Most "AI support" products stop at **generating an answer**. They do not investigate, do not take action, do not know when to stop and hand off, and do not learn from what was resolved yesterday.

ACSRP is a multi-agent platform that behaves like a **production AI Customer Resolution Engineer**. For every request it can:

> **Understand → Investigate → Retrieve → Decide → Act → Escalate → Remember**

It classifies and prioritises the request, retrieves the right documentation and similar past tickets, pulls customer context, troubleshoots, builds a resolution plan, executes approved actions through governed tools (MCP), escalates high-risk cases to humans, and stores what it learned for the next customer.

The same application is deployed on **AWS, Azure and GCP** using Terraform, so learners see how one architecture maps to three clouds.

---

## 2. Business Context (BRD)

### 2.1 Problem Statement

| # | Problem | Business impact |
|---|---|---|
| P1 | High ticket volume, much of it repetitive (password resets, billing questions, order status, how-to) | Agent cost scales linearly with volume |
| P2 | Slow first response and resolution times | CSAT drop, churn, SLA penalties |
| P3 | Knowledge spread across docs, wikis, old tickets and agent heads | Inconsistent answers, long onboarding |
| P4 | Chatbots answer but cannot act (refund, reset, reship, update account) | Customers still wait for a human |
| P5 | No reliable judgement on when AI should stop | Risky automated actions or over-escalation |
| P6 | Resolved cases are not reused | The same investigation is repeated many times |
| P7 | No auditability of AI decisions | Compliance and trust blockers |

### 2.2 Business Objectives

| ID | Objective | Target (12 weeks post go-live, reference tenant) |
|---|---|---|
| BO-1 | Automate resolution of routine tickets end-to-end | ≥ 40% autonomous resolution rate (L1 categories) |
| BO-2 | Reduce first response time | P50 < 30 s, P95 < 2 min for chat/app channels |
| BO-3 | Reduce mean time to resolution (MTTR) | −35% vs baseline |
| BO-4 | Keep quality high | CSAT ≥ 4.3/5 on AI-resolved tickets; reopen rate < 8% |
| BO-5 | Zero unsafe autonomous actions | 0 high-risk actions executed without approval |
| BO-6 | Make human agents faster | Agent handle time −25% via summaries and draft plans |
| BO-7 | Control AI cost | Average LLM cost per ticket < US$0.08 |

### 2.3 Stakeholders

| Stakeholder | Interest |
|---|---|
| Customers / end users | Fast, correct, consistent resolution |
| Support agents (L1/L2) | Copilot, summaries, fewer repetitive tickets |
| Support supervisors / team leads | Queue health, SLA, approvals, quality |
| Support operations / admin | Configuration, policies, knowledge base, integrations |
| Engineering / SRE | Reliability, deployability, observability |
| Security & compliance | PII handling, audit trails, RBAC |
| Finance | AI and cloud cost per ticket |
| Learners (series audience) | A reference architecture they can rebuild and extend |

### 2.4 Scope

**In scope (v1.0)**
- Ingestion from web chat widget, email (inbound webhook), REST API (apps), and a ticketing-system connector (mock Zendesk/Jira-style adapter)
- Six-agent LangGraph system (Supervisor, Customer, Knowledge/RAG, Troubleshooting, Resolution, Escalation)
- Advanced + agentic RAG over product docs and resolved tickets (hybrid search + reranking)
- Action execution via MCP tool servers with human-in-the-loop approvals
- Customer memory (short-term + long-term)
- Support dashboard (Next.js) for agents, supervisors and admins
- Auth, RBAC, rate limiting, guardrails, logging, tracing, evaluation
- Docker, Terraform, CI/CD, deployment to AWS, Azure and GCP

**Out of scope (v1.0)**
- Voice/telephony channel (planned v2)
- Native integrations with every commercial helpdesk (one reference adapter only)
- Fine-tuning of foundation models
- Multi-language UI (agents may still answer in the customer's language)
- Real payment processing (refund tool hits a sandboxed billing service)

### 2.5 Assumptions & Constraints
- LLM access through a provider-agnostic gateway (OpenAI / Anthropic / Azure OpenAI / Vertex AI / Bedrock); model is configuration, not code.
- Reference tenant uses synthetic but realistic data (product docs, ~5–10k historical tickets, customer and order records).
- All sensitive actions run against sandboxed back-office systems.
- Each cloud deployment must use the same container images and the same application configuration contract.

---

## 3. Personas

| Persona | Description | Key needs |
|---|---|---|
| **Maya — Customer** | Uses chat or email to get help | Quick answers, no repetition of context, clear next steps |
| **Ravi — L1 Support Agent** | Handles queue, reviews AI drafts | Ticket summary, suggested plan, one-click approve/edit |
| **Elena — Support Supervisor** | Owns SLA and quality | Approval queue, escalations, dashboards, QA sampling |
| **Sam — Support Ops Admin** | Configures the platform | Knowledge sources, policies, tool permissions, routing rules |
| **Priya — Platform Engineer** | Runs it in production | Health, traces, cost, deploy pipeline, incident tooling |

---

## 4. User Journeys

### J1 — Autonomous resolution (low risk)
1. Maya writes in chat: "I was charged twice for my October subscription."
2. Supervisor Agent classifies: *Billing / Duplicate charge / Severity P3 / Sentiment negative*.
3. Customer Agent loads profile, plan, last invoices, open tickets and memory.
4. Troubleshooting Agent confirms two captured charges for the same invoice.
5. Knowledge Agent retrieves the refund policy and three similar resolved tickets.
6. Resolution Agent proposes: refund duplicate charge (US$29), within auto-approve limit per policy.
7. Policy engine marks action **low risk → auto-approved**; MCP `billing.refund` executes.
8. Customer receives confirmation; ticket resolved, summary written, memory updated.

### J2 — Human-in-the-loop approval
Same flow, but refund is US$480 (above auto limit). The graph **pauses**, creates an approval request. Elena approves from the dashboard; the graph resumes from checkpoint and executes.

### J3 — Escalation
Customer reports suspected account takeover. Severity P1, risk *critical*. Escalation Agent hands off immediately to the security queue with a structured case brief; AI takes no account actions and tells the customer a specialist is on it.

### J4 — Agent copilot
Ravi opens a complex ticket the AI could not resolve. He sees: summary, timeline, retrieved evidence with citations, hypotheses tested, recommended next step, and a draft reply.

### J5 — Learning loop
After a ticket is closed with positive feedback, its resolution is distilled into a "resolution card" and indexed so future similar tickets retrieve it.

---

## 5. Functional Requirements

Priority: **M** = Must, **S** = Should, **C** = Could.

### 5.1 Intake & Understanding
| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Accept requests from chat widget, email webhook, REST API and ticketing connector, normalised into one `Ticket` model | M |
| FR-02 | Detect language, intent, product area, category/subcategory and entities (order ID, invoice ID, device, error code) | M |
| FR-03 | Classify severity (P1–P4) and sentiment; detect urgency signals (outage, security, legal, churn threat) | M |
| FR-04 | Deduplicate / thread messages into existing tickets | S |
| FR-05 | Ask clarifying questions when required information is missing (max 2 turns before handoff) | M |

### 5.2 Investigation & Retrieval
| ID | Requirement | Pri |
|---|---|---|
| FR-06 | Search product documentation with hybrid retrieval (dense + BM25) and reranking | M |
| FR-07 | Search previously resolved tickets and resolution cards | M |
| FR-08 | Retrieve customer profile, subscriptions, orders, invoices, device/service status via tools | M |
| FR-09 | Agentic RAG: query rewriting, multi-hop retrieval, self-check of retrieved evidence sufficiency | M |
| FR-10 | Every factual claim in a customer reply is grounded with a citation to a source chunk | M |
| FR-11 | Check system status / known incidents before troubleshooting | S |

### 5.3 Troubleshooting & Resolution
| ID | Requirement | Pri |
|---|---|---|
| FR-12 | Generate hypotheses, run diagnostic tools, and record findings | M |
| FR-13 | Produce a structured **Resolution Plan** (steps, actions, risk, expected outcome, confidence) | M |
| FR-14 | Draft customer reply in brand tone, customer's language | M |
| FR-15 | Execute actions only through registered MCP tools with schema-validated arguments | M |
| FR-16 | All actions are idempotent (idempotency key per ticket+action) | M |
| FR-17 | Verify action outcome and report back to customer | M |

### 5.4 Human-in-the-Loop & Escalation
| ID | Requirement | Pri |
|---|---|---|
| FR-18 | Policy engine assigns each action a risk tier: *low / medium / high / prohibited* | M |
| FR-19 | Low = auto-execute; medium = agent approval; high = supervisor approval; prohibited = never | M |
| FR-20 | Graph pauses on approval and resumes from a durable checkpoint | M |
| FR-21 | Approvers can approve, reject, or edit arguments; decisions are audited | M |
| FR-22 | Escalate when: confidence < threshold, P1, security/legal/fraud, repeated failure, explicit human request, negative sentiment spike | M |
| FR-23 | Escalation creates a case brief (summary, evidence, attempted steps, recommended owner) and routes to a queue | M |
| FR-24 | SLA timers and approval timeouts with auto-escalation | S |

### 5.5 Memory & Learning
| ID | Requirement | Pri |
|---|---|---|
| FR-25 | Short-term (conversation) memory per ticket thread | M |
| FR-26 | Long-term customer memory: preferences, environment, past issues, promises made | M |
| FR-27 | Customer can request memory deletion (right to erasure) | M |
| FR-28 | Generate ticket summary on resolve/escalate | M |
| FR-29 | Distil successful resolutions into resolution cards, indexed for retrieval after review | S |
| FR-30 | Capture CSAT and agent feedback, linked to traces for evaluation | M |

### 5.6 Dashboard (Web)
| ID | Requirement | Pri |
|---|---|---|
| FR-31 | Ticket inbox with filters (status, severity, channel, assignee, AI state) | M |
| FR-32 | Ticket detail: conversation, AI timeline, evidence with citations, plan, actions | M |
| FR-33 | Approval queue with diff view of proposed action arguments | M |
| FR-34 | Escalation queue | M |
| FR-35 | Analytics: volume, autonomous rate, FRT, MTTR, CSAT, cost, escalation reasons | M |
| FR-36 | Admin: knowledge sources, ingestion jobs, policies, tool registry, users and roles | M |
| FR-37 | Customer-facing chat widget (embeddable) | M |
| FR-38 | Real-time updates (WebSocket/SSE) | S |

### 5.7 Administration
| ID | Requirement | Pri |
|---|---|---|
| FR-39 | Upload/connect knowledge sources (PDF, Markdown, HTML, URL crawl); scheduled re-index | M |
| FR-40 | Versioned prompts and policies with rollback | S |
| FR-41 | Feature flags per tenant (autonomy level: copilot-only / supervised / autonomous) | M |
| FR-42 | Multi-tenancy (tenant isolation at data and vector index level) | S |

---

## 6. Non-Functional Requirements

| Category | ID | Requirement |
|---|---|---|
| Performance | NFR-01 | Chat first token P95 < 3 s; full resolution plan P95 < 20 s (excluding approval waits) |
| | NFR-02 | Retrieval (hybrid + rerank) P95 < 800 ms |
| Scalability | NFR-03 | 50 concurrent conversations per API replica; horizontal scaling to 1,000+ |
| | NFR-04 | 100k tickets/month per tenant; 1M+ indexed chunks |
| Availability | NFR-05 | 99.9% API availability; graceful degradation to "human handoff" mode if LLM provider fails |
| Reliability | NFR-06 | Durable graph checkpoints; no lost tickets; at-least-once background processing with idempotency |
| Security | NFR-07 | OIDC/JWT auth, RBAC, TLS 1.2+, encryption at rest, secrets in cloud secret manager |
| | NFR-08 | OWASP API Top 10 controls; prompt-injection defences on all untrusted content |
| Privacy | NFR-09 | PII detection and redaction in logs/traces; data residency per tenant; retention policies |
| Rate limiting | NFR-10 | Per-tenant, per-user and per-IP limits; LLM token budgets per tenant |
| Observability | NFR-11 | Structured logs, metrics, distributed traces (OpenTelemetry) and LLM traces (Langfuse/LangSmith) with ticket correlation ID |
| Evaluation | NFR-12 | Offline eval suite gates every release; online quality monitoring |
| Cost | NFR-13 | Per-ticket token and cost accounting; model routing (small model for classification) |
| Portability | NFR-14 | Same images on AWS/Azure/GCP; cloud-specific code isolated behind adapters |
| Maintainability | NFR-15 | ≥ 80% unit test coverage on core services; typed contracts (Pydantic/TypeScript) |
| Accessibility | NFR-16 | Dashboard and widget meet WCAG 2.1 AA |

---

## 7. AI Requirements

| Area | Requirement |
|---|---|
| Structured outputs | All agent outputs validated against Pydantic schemas; retry with repair on validation failure |
| Guardrails (input) | Prompt-injection detection, PII detection, toxicity, off-topic filter, jailbreak patterns |
| Guardrails (output) | Groundedness check, policy compliance (no promises outside policy), PII leakage, tone |
| Guardrails (action) | Tool allow-list per agent, argument validation, risk-tier policy, spend limits |
| Model routing | Small/fast model for classification and guardrails; strong model for planning; embedding + reranker models configurable |
| Determinism | Temperature ≤ 0.2 for decisions; seeds/versions recorded in traces |
| Explainability | Every decision stores rationale, evidence IDs and confidence |
| Fallbacks | Provider failover; retrieval-only answer; human handoff |

---

## 8. Success Metrics & Evaluation

| Metric | Definition | Target |
|---|---|---|
| Autonomous resolution rate | Resolved without human touch / total eligible | ≥ 40% |
| Escalation precision | Escalations judged necessary by humans | ≥ 85% |
| Escalation recall | High-risk tickets that were escalated | ≥ 98% |
| Classification accuracy | Category & severity vs labelled set | ≥ 90% / ≥ 92% |
| Retrieval quality | Recall@10 / nDCG@5 on golden queries | ≥ 0.90 / ≥ 0.75 |
| Faithfulness | Answer claims supported by context (RAGAS-style) | ≥ 0.92 |
| Tool-call correctness | Correct tool + valid args on eval set | ≥ 95% |
| Unsafe action rate | Actions violating policy | 0 |
| CSAT (AI-resolved) | Post-resolution survey | ≥ 4.3 / 5 |
| Reopen rate | Reopened within 7 days | < 8% |
| Cost per ticket | LLM + embedding + rerank cost | < US$0.08 |

---

## 9. Release Plan (aligned to the series)

| Phase | Deliverables |
|---|---|
| 0. Problem & PRD | This document, success metrics, synthetic dataset spec |
| 1. Architecture | HLD, LLD, ADRs |
| 2. Foundations | Repo, FastAPI skeleton, Postgres schema, Redis, auth, Next.js shell |
| 3. Knowledge | Ingestion pipeline, hybrid retrieval, reranking, eval set |
| 4. Agents | LangGraph supervisor + 5 agents, structured outputs, tools |
| 5. MCP & Actions | MCP servers (CRM, billing, orders, ticketing, status), policy engine, HITL |
| 6. Memory & Learning | Short/long-term memory, summaries, resolution cards |
| 7. Guardrails & Security | Input/output/action guardrails, RBAC, rate limiting |
| 8. Testing & Evaluation | Unit, integration, agent evals, red-team set, CI gates |
| 9. Containerisation & IaC | Docker, Compose, Terraform modules per cloud |
| 10. CI/CD | GitHub Actions: build, test, eval, scan, deploy |
| 11. Multi-cloud deploy | AWS, Azure, GCP environments |
| 12. Observability & Ops | Dashboards, alerts, runbooks, cost monitoring |

**Autonomy rollout per tenant:** Copilot-only → Supervised (all actions need approval) → Autonomous (policy-based).

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hallucinated policies or promises | M | H | Grounding checks, citations, policy guardrail, low temperature |
| Prompt injection via email/attachments/docs | H | H | Content isolation, injection classifier, tool allow-lists, no tool args from untrusted text without validation |
| Wrong or duplicate action (e.g. double refund) | M | H | Risk tiers, HITL, idempotency keys, spend caps, post-action verification |
| PII leakage to logs/LLM | M | H | Redaction, data minimisation, provider data controls |
| LLM provider outage / latency | M | M | Gateway failover, timeouts, handoff mode |
| Cost runaway (loops) | M | M | Max graph steps, token budgets, loop detection |
| Knowledge staleness | M | M | Scheduled re-index, doc versioning, freshness metadata |
| Over-escalation reduces value | M | M | Threshold tuning with eval data, supervisor feedback |
| Multi-cloud drift | M | M | Single Terraform module interface, identical images, conformance tests |

---

## 11. Compliance & Governance
- Audit log for every AI decision, tool call, approval and data access (immutable, append-only).
- Data retention configurable per tenant (default: conversations 1 year, traces 30 days, audit 7 years).
- Right to access / erasure for customer memory.
- Model and prompt version recorded per decision.
- Alignment targets: GDPR/PIPEDA principles, SOC 2-style controls (reference implementation, not certification).

---

## 12. Acceptance Criteria (v1.0)
1. All **Must** functional requirements implemented and demonstrated on the reference tenant.
2. Offline eval suite passes all targets in §8 on the golden dataset.
3. Red-team suite: 0 successful prompt-injection-to-action exploits.
4. Load test meets NFR-01/03 on one cloud; smoke tests pass on all three clouds.
5. Dashboards and alerts live; runbooks written for top 5 failure modes.
6. Same Git commit deployed to AWS, Azure and GCP via CI/CD.

---

## 13. Glossary
| Term | Meaning |
|---|---|
| Agentic RAG | Retrieval where an agent decides what/when/how to retrieve, rewrites queries and checks sufficiency |
| HITL | Human-in-the-loop approval of agent actions |
| MCP | Model Context Protocol — standard interface exposing tools/resources to agents |
| Resolution card | Distilled, reviewed record of how a past issue was resolved |
| Risk tier | Policy classification controlling whether an action needs approval |
| Checkpoint | Persisted LangGraph state allowing pause/resume |
