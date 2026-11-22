# MEMORY.md — CloudDesk Project 1

Durable facts for this repository. `CLAUDE.md` wins if this file drifts. Update this file when a decision, demo fact, or delivery status changes. Do not store secrets, customer payloads, or raw ticket bodies here.

## Product

- Fictional SaaS: **CloudDesk** (team collaboration, cloud file storage, billing, workspaces, API access).
- Users of this product are **support agents**. Customers do not use the console in v1.
- Pipeline for every ticket: Understand → Classify → Investigate → Retrieve → Troubleshoot → Decide → Resolve → Act → Escalate → Remember.
- v1 integrations are mocks. The product does not send real email and does not issue real refunds.
- v1 is English-only and has no customer-facing chat widget.
- Business metrics are tracked, never hard-coded: percent of tickets resolved without a human edit, median time to first response, escalation precision, refund approvals per week. Refunds are never zero-touch.

## Locked decisions

- Three tiers: Next.js 15 on `:3000`, FastAPI on `:8000`, then PostgreSQL/SQLite, Redis/fakeredis, Qdrant/in-memory, and `get_llm`.
- The workflow is a LangGraph graph in `agents/graph.py` with six specialists.
- Demo runtime is offline: `LLM_PROVIDER=fake`, `VECTOR_STORE=memory`, `USE_FAKE_REDIS=true`, SQLite, `InMemorySaver` when `CHECKPOINT_DB_PATH=:memory:`.
- SQLAlchemy models stay portable: JSON columns, `String(36)` UUIDs, same code on SQLite and Postgres.
- Postgres DDL in `database/schema.sql` is the cloud schema. SQLite tables are created at startup.
- The backend uses the service-role key on the server. The browser receives only the anon key.
- JWT is HS256. Demo tokens expire in 8 hours.
- Background workflows run in-process for v1.
- Image tags equal the git SHA once delivery exists. Nothing has been built or tagged yet.
- Stage 17 (Agentic DevOps) is optional and depends on stages 13–16. It is outside core Project 1 completion.
- 2026-10-25 — F14 / observability: process settings are `get_settings()` in `backend/app/core/config.py` (cached). JSON logs come from `setup_logging()` and `log_context()` in `backend/app/core/logging.py`. Every line includes `request_id` and `workflow_id` (`null` when unset). `model_dump()` redacts secrets and URL passwords; connection code reads the attributes.
- 2026-10-25 — N3: `RequestIdMiddleware` echoes a safe `X-Request-ID` or assigns a UUID, binds `log_context`, and sets the header on application responses, including 404 and 500. CORS sits outside it and exposes the header. `/health` and `/health/live` do not probe dependencies. `/health/ready` returns 200 `ready` or 503 `degraded` from configuration checks until the database, Redis, vector store, and LLM clients exist. Those details never include a URL, password, or API key.
- 2026-11-21 - F1/F4 (Phase 2): ids are `varchar(36)` UUID text in Postgres too (not `uuid`), so the same SQLAlchemy models run on asyncpg and SQLite. Sample-data ids are `uuid5` of a key, so reseeding cannot duplicate rows. SQLite engines turn `PRAGMA foreign_keys` on so FK errors match Postgres.
- 2026-11-21 - Phase 2: the demo bootstrap loads profiles, customers, subscriptions, workspaces, products, support_articles (15 KB articles), incidents, tickets and one ticket_message each. It runs only when `DEMO_MODE=true` and there are no customers and no tickets. Tickets start `new` with no category or severity; the workflow sets them.
- 2026-11-21 - Phase 2: `sample_data/previous_resolutions.json` is NOT loaded into the database (there is no table for it among the 16). The Knowledge Agent reads it directly for similar cases in Phase 8.
- 2026-11-21 - Phase 2: `database/seed.sql` is generated from the same records by `scripts/generate_seed_sql.py`; a test fails if it is stale. `database/schema.sql` was bootstrapped from the models and is now hand-owned. Migration 0001 copies it, 0002 copies `rls_policies.sql`.

## Roles

Enforced by `require_role` in `backend/app/core/security.py` (`viewer 1 < agent 2 < admin 3`).

| Role | Access |
|---|---|
| `viewer` | Read tickets, customers, knowledge, and audit |
| `agent` | Viewer access, plus run workflows, reply, approve/reject, and escalate |
| `admin` | Agent access, plus reindex knowledge and settings |

Demo users: `admin@clouddesk.demo`, `sam.agent@clouddesk.demo`, `vic.viewer@clouddesk.demo`.

## Domain constants

Categories, exactly these ten, defined first in `backend/app/schemas/common.py`:

`login_issue`, `billing`, `api_failure`, `workspace_permissions`, `storage_quota`, `integration`, `feature_request`, `account`, `security`, `other`.

- Statuses: `new`, `in_progress`, `waiting_on_customer`, `waiting_on_approval`, `escalated`, `resolved`, `closed`.
- Severity: `low`, `medium`, `high`, `critical`.
- Channels: `email`, `chat`, `web`, `api`.
- Plans in the demo set: free, pro, business, enterprise. Eight customers. Thirteen tickets.

| Ticket | What it must exercise |
|---|---|
| CD-1001 | Login issue, active incident, enterprise |
| CD-1002 | Billing refund; approval gate on `create_refund_request` |
| CD-1003 | API 429; rate-limit docs |
| CD-1004 | Storage quota and subscription limits |
| CD-1005 | Security; policy escalation |
| CD-1006 | Data loss; policy escalation |
| CD-1007 | Workspace permissions |
| CD-1008 | Integration failure |
| CD-1009 | Account deletion / GDPR; policy escalation |
| CD-1010 | Feature request; low severity by policy |
| CD-1011 | Payment dispute; policy escalation |
| CD-1012 | MFA recovery article |
| CD-1013 | Prompt injection; ticket text stays data |

Policy cases that rules decide, and the model must not override: dispute, deletion, security, data loss, legal, enterprise outage.

## Workflow facts

Graph order:

`understand_ticket` → `classify_severity` → `customer_context` → `knowledge_retrieval` → `troubleshooting` → `resolution_planning` → `risk_check`, then either `escalation`, `human_approval`, or `execute_resolution`, then `ticket_summary` → `memory_update` → END.

- `human_approval` calls `interrupt()`. Resume uses `Command(resume=…)`.
- Rejection of an approval routes to escalation.
- Node ids are the `completed_nodes` values the UI renders.
- `GET /api/v1/agents` is fed by `GRAPH_NODES` / `GRAPH_EDGES`.
- A second run while status is `waiting_on_approval` returns 409. Resuming a run that is not paused returns 409.
- `WorkflowTracer` never raises. Event names: `node_started`, `node_completed`, `tool_called`, `llm_called`, `approval_requested`, `approval_resolved`, `error`, `workflow_completed`.
- Exposed to operators: decisions, tool calls and results, evidence with scores, node timings, token counts, errors.
- Hidden: raw prompts, hidden chain-of-thought, other customers’ data, secrets.

Tools:

| Tool | Writes | Approval |
|---|---|---|
| `get_customer`, `get_subscription`, `get_ticket_history` | no | no |
| `search_docs`, `check_service_status` | no | no |
| `update_ticket` | tickets | no |
| `reset_demo_setting` | workspace admin | yes |
| `create_refund_request` | billing | yes |
| `create_escalation` | escalations | no |

Unknown tools require approval. Timeout is `TOOL_TIMEOUT_SECONDS`.

## RAG and memory facts

- Knowledge source: `sample_data/knowledge_base/*.md` (15 articles) with YAML front-matter `title`, `category`, `tags`, `summary`.
- Chunk on headings, then 900-character windows with 150-character overlap. Prefix each chunk with `"{title} - {heading}"`.
- Retrieval: semantic ∪ BM25 → reciprocal rank fusion (`k=60`) → heuristic rerank → optional LLM rerank → one hit per article.
- Modes: `hybrid` (default), `semantic`, `keyword`.
- Fake embeddings: hashed bag-of-words, 384 dimensions. Changing the embedding model requires admin `POST /knowledge/reindex`, which recreates the collection.
- Evidence fields: `id`, `title`, `source` (`kb://slug#section`), `snippet`, `score`, `url` (`/knowledge/<id>`), `article_id`.
- Customer-facing policy claims cite knowledge articles.
- Short-term memory TTL is 24 hours. Retrieval cache TTL is 300 seconds. Cache key shape: `rag:{mode}:{category}:{top_k}:{query}`.
- Long-term note types: `preference`, `past_issue`, `troubleshooting`, `note`. Recall up to 10 notes. After a run, store the past issue, the first three troubleshooting steps, and a resolution note.
- `SECRET_PATTERNS` covers card numbers, API keys, and passwords.

- 2026-11-21 - F5 (Phase 5): `rag/` sits at the repo root, so `pyproject.toml` pytest `pythonpath` is `["backend", "."]` and the Makefile runs uvicorn as `python -m uvicorn ... --app-dir backend` from the root. BM25 is a small in-repo implementation (no `rank_bm25` dependency). `VectorStoreService` has a sixth method, `list_chunks`, because keyword search needs the corpus. `retrieve(category=)` is a hard filter; `category_hint=` only nudges the rerank. `POST /knowledge/reindex` returns `{indexed: chunks, articles}`.

## Evaluation bar

These fail the build: classification accuracy ≥ 0.80, retrieval hit-rate@3 ≥ 0.75, escalation correctness ≥ 0.90, citation rate ≥ 0.90, grounding rate ≥ 0.90.

Cases live in `datasets/eval_cases.json` and each case needs a valid `expected_category`.

## Environment defaults worth remembering

- `APPROVAL_REQUIRED_FOR_REFUNDS=true`, `MAX_REFUND_WITHOUT_APPROVAL=0`.
- Demo rate limit: `RATE_LIMIT_PER_MINUTE=120`.
- `QDRANT_COLLECTION=clouddesk_knowledge`.
- `get_settings()` is cached. A `.env` change requires a server restart.
- Middleware order, outermost last: CORS → RequestId → RateLimit → Audit.
- Health: `/health`, `/health/live` (no I/O), `/health/ready` (db, redis, vector store, llm).

## Honest status

Update each row in place. Do not mark a row done from intention.

| Surface | State on 2026-11-21 |
|---|---|
| Implemented | Phase 1 (settings, JSON logging, health, request id, offline harness, Makefile, `.env.example`) and Phase 2 (16 SQLAlchemy models, `database/schema.sql`, RLS, migrations 0001-0002, repositories, `sample_data/`, `seed_service`, lifespan bootstrap, `scripts/seed.py`, generated `database/seed.sql`). |
| Validated locally | `.venv/Scripts/python.exe -m pytest -q`: 68 passed offline; `ruff check .` clean. `make` is not installed on this Windows machine, so Makefile targets are unrun; the `make seed` command was run directly (`scripts/seed.py`) and is idempotent. `make demo` does not exist yet. Postgres DDL, RLS and `seed.sql` were checked against the models by tests only; they have never been run on a real Postgres or Supabase. |
| Not merged | Phase 2 work sits on branch `feat/Phase2_Persistence_and_demo_data`, uncommitted. |
| Repair | The Phase 1 merge into `development` had left `main.py`, `health.py`, `request_id.py`, `pyproject.toml`, `uv.lock` and `tests/api/test_health.py` as two spliced versions (no test could be collected). They were repaired on the Phase 2 branch to the richer design in `docs/API_CONTRACT.md`; `uv.lock` was regenerated. |
| Cloud credentials | None used. |
| Applied to a real account | Nothing. |
| GitHub Actions | Workflow files are not in the repo. None have been executed. |
| Phase 4 (2026-11-21) | Implemented: `GET/POST /tickets`, `GET/PATCH /tickets/{id}` (id or `CD-####`), `/events`, `/reply`, `/request-info`, `/escalate`, `GET /customers`, `GET /customers/{id}`; services `ticket_service`/`customer_service`; schemas `records`/`tickets`/`customers`; 36 new API tests; full suite 127 passed, ruff clean. Contract reshaped to match the DB model. Not built yet: `/run`, `/workflow` (Phase 10), approvals, knowledge, dashboard, agents, audit, settings routes. Branch `feat/Support_API`, uncommitted. |
| Phase 5 (2026-11-21) | Implemented: `rag/` (`chunking`, `text`, `vector_store`, `retriever`, `ingest`), `scripts/ingest.py` (`make ingest`), `/knowledge/articles`, `/articles/{id}`, `/search`, `/reindex` (admin), index built at startup. 37 new tests; full suite 164 passed, ruff clean. Measured on the 12 demo tickets that have an article: hybrid hit@3 = 12/12, hit@1 = 11/12 (small set written alongside the articles, so optimistic). Corpus: 15 articles, 46 chunks. Not done: `QdrantVectorStore` is written but never run (`qdrant-client` is not a dependency); no real embedding provider (only `fake`); LLM rerank is a hook with no caller until the Knowledge Agent (Phase 8 in PLAN_PHASE.md, P9-4 in TASKS.md); similar cases are also there. Branch work uncommitted. |
| Phase 7 (2026-11-21) | Implemented: `agents/rules.py` (6 escalation rules with named teams, `rule_category`, `rule_severity`/`raise_severity`), `agents/prompts.py` (`SECURITY_PREAMBLE`, `wrap_untrusted`), `backend/app/core/guardrails.py` (`scan_for_injection`, `strip_injection`, `validate_customer_output`, `scrub`, `SECRET_PATTERNS`). Output-validation failure = risk `high`. 102 new tests; full suite 294 passed, ruff clean. Regex-based; nothing calls them until Phases 8-10. CD-1006 and CD-1013 have no rule category by design. Uncommitted. |
| Phase 9 (2026-11-22) | Implemented (TASKS.md Phase 9 = PLAN_PHASE Phase 8): `backend/app/schemas/workflow.py`, `backend/app/core/llm.py` (`call_structured`, fake provider via an `offline=` function the caller supplies, cost 0.0), `agents/specialists/` (Supervisor, Customer, Knowledge, Troubleshooting, Resolution, Escalation), specialist prompts in `agents/prompts.py`, `datasets/eval_cases.json` (27 cases). 51 new tests; full suite 355 passed, ruff clean. On the dataset: classification 27/27 and escalation 27/27, but the cases were written beside the rules, so this is optimistic. Not done: no real LLM provider has ever been called (`get_llm` untested); no graph nodes, tracer or `/run` yet (Phase 10); `make demo` still does not exist. Uncommitted on `feat/Phase9_Specialist_agents`. |
| Phase 10 (2026-11-22) | Implemented (TASKS.md Phase 10 = PLAN_PHASE Phase 9): `agents/state.py`, `risk.py`, `checkpointer.py`, `graph.py`, `nodes/`, `backend/app/core/observability.py` (`WorkflowTracer`), `services/workflow_service.py` + `workflow_view.py`, `POST /tickets/{id}/run` (202) and `GET /tickets/{id}/workflow`, `TicketDetail.workflow`. Validated locally: 26 new tests, 380 pass offline, ruff clean. Added dependency `langgraph-checkpoint-sqlite`. NOT done: `human_approval` interrupt, `escalation` node and filing escalations, approve/reject API, resume (Phase 11); every route currently goes to `execute_resolution`, which holds approval-required actions as `awaiting_approval`. File-backed checkpointer and the already-running 409 are untested; a crashed run stays `running` and blocks `/run`. |
| Phase 11 (2026-11-22) | Implemented (TASKS.md Phase 11 = PLAN_PHASE Phase 10): `agents/nodes/approval.py` (`human_approval` with `interrupt()` and the `escalation` node), graph routes `approval -> human_approval`, `escalation -> escalation`, approved -> `execute_resolution`, rejected -> `escalation`; `execute_resolution` runs an approval-required action only when the DATABASE holds an approved request (`approved=True` into `ToolRegistry`); `workflow_service` (`_drive`, `_handle_interrupt`, `resume_workflow`); `approval_service.decide` (one conditional UPDATE claims the request, so a double click is 409); `/approvals` list, get, approve, reject; `scripts/demo.py` + `make demo [TICKET=]`. Validated locally: 28 new tests, 408 pass offline, ruff clean; `scripts/demo.py` run directly for CD-1002 (pause, approve, refund once) and CD-1005 (escalation). `make` itself was not run. Not built: any console screen for the buttons (Phases 12-13), restart-resume of a paused run from the SQLite checkpoint (not tested), a worker process (approve resumes inside the request), real-LLM run, cloud. |
| Phase 12 (2026-11-22) | Implemented (TASKS.md Phase 12 = console shell; PLAN_PHASE Phase 12 first half): `frontend/` Next.js 15 + Tailwind 3, hand-written `components/ui/` kit (no UI library, no gradients), `lib/{api,types,hooks,format,cn}.ts`, `components/layout/{nav,AuthProvider,Shell}`, pages `/login`, `/dashboard`, `/tickets`, `/tickets/[id]` (read-only), `/customers`, `/customers/[id]`, `/knowledge`, `/escalations`, `/agents`, `/audit`, `/settings` (admin only), `/api/health`. API client: bearer token in localStorage, 401 -> `/login?reason=expired`, GET-only network retry (2x), `NetworkError`; `isNotBuilt()` shows a friendly empty state for contract routes the backend lacks. Validated locally: 15 vitest tests, `tsc`, `next lint`, `next build` clean. NOT done: live browser pass against the running backend (not run); the dashboard, escalations, agents, audit and settings routes do not exist in the backend yet, so those 5 pages show 'Not available yet'; no ticket workflow screen, approve/reject/reply buttons or WorkflowSteps (Phase 13); no frontend Dockerfile (Phase 14); `frontend/.env.example` not created (blocked by a permission rule). |
| Phase 13 (2026-11-22) | Implemented (TASKS.md Phase 13 = ticket workflow screen; PLAN_PHASE Phase 12 second half): `app/(dashboard)/tickets/[id]/page.tsx` three-column screen, `components/ticket/{WorkflowSteps,WorkflowPanel,ApprovalBar,ReplyComposer}`, `lib/workflow.ts` (`deriveSteps`, `shouldPoll`, `canDecide`), new `api` calls (run, workflow, approve, reject, reply, requestInfo, escalate) and workflow/approval types. 2 s poll only while `running`; Approve/Reject only when approval pending, disabled for viewer; reply draft editable. No backend change. Validated locally: 32 vitest tests (17 new), `tsc`, `next lint`, `next build` clean; backend 408 pass. NOT done: live browser pass against the running backend (an HTTP check was attempted and blocked, so not run), `/events` timeline not drawn, reply/request-info/escalate share one text box, no Dockerfile or cloud (Phase 14). |
| Phase plan (older note) | Phases 1 and 2 validated locally. Phases 3-13 not started. `CLAUDE.md` section 19 still says Phase 1 in progress and Phase 2 not started; update it between sessions. |

## Open questions from `CLAUDE.md` §20

- A Project 1 `README.md` was referenced by the course and was not supplied. Command names in `CLAUDE.md` §14 still need to be checked against it when it appears.
- Course paths `../docs/`, `../deployment-agent/`, and `../shared-infrastructure/` sit outside this repo. They are not copied in yet.
- ~~Table counts disagree across the course notes~~ Closed 2026-11-21: `database/schema.sql` defines 16 tables and RLS is enabled on all 16 (`profiles` included). `tests/unit/test_schema_parity.py` keeps models and DDL in agreement.
- Stage documents 00–17 are not in this repo. `PLAN_PHASE.md` is derived from `CLAUDE.md`, not from those missing files.

## Update protocol

- Record a new locked decision with the date and the requirement id it serves.
- When a phase exits, set its status in `PLAN_PHASE.md` and add one line here under Honest status.
- When a demo ticket’s expected behaviour changes, change the ticket table above and the matching test together.
- Leave secrets, tokens, connection strings, and ticket bodies out of this file.
