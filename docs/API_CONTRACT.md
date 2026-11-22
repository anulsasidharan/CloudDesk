# Project 1 – Backend API Contract (v1)

Base URL: `http://localhost:8000` (env `NEXT_PUBLIC_API_URL`). All routes below are prefixed with `/api/v1`
except the health routes. All non-auth routes require `Authorization: Bearer <jwt>`.
Every response carries `X-Request-ID`. A caller-supplied value is echoed when it is 1–128 characters
from `A-Za-z0-9._:-`; any other value is replaced with a UUID. CORS exposes `X-Request-ID`.
Errors: `{ "detail": string }` with proper HTTP status.

## Health (no prefix, no auth)
| Method | Path | Response |
|---|---|---|
| GET | `/health` | 200 `{status:"ok", service, version, environment}` |
| GET | `/health/live` | 200 `{status:"alive"}`. No dependency I/O. |
| GET | `/health/ready` | 200 `{status:"ready", checks:{database, redis, vector_store, llm}}` when every check is `ok`. 503 `{status:"degraded", checks:...}` otherwise. Each check is `{status:"ok"|"error", detail?}`. Details never include URLs, passwords, or API keys. |

## Auth
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/demo-login` | `{email?: string, role?: "admin"|"agent"|"viewer"}` | `{access_token, token_type:"bearer", expires_in: 28800, user: User}` (only when `DEMO_MODE=true`; 404 otherwise; email wins over role; neither → demo agent; unknown email → 404) |
| GET | `/auth/me` | – | `User` |

`User = { id, email, full_name, role, avatar_url? }`

## Dashboard
`GET /dashboard/summary` → `{ open_tickets, resolved_today, pending_approvals, escalations_open, avg_resolution_minutes, by_severity:{low,medium,high,critical}, by_category:{[category]:number}, recent_tickets: TicketSummary[], agent_activity: WorkflowEvent[] }`

## Tickets
| Method | Path | Notes |
|---|---|---|
| GET | `/tickets?status=&severity=&search=&page=1&page_size=20` | `{ items: TicketSummary[], total, page, page_size }`. Newest first. `search` matches subject, body or number (case-insensitive). `page>=1`, `1<=page_size<=100`; an unknown `status` or `severity` is **422**. *(Implemented, Phase 4)* |
| POST | `/tickets` | body `{ customer_id, subject, body, channel?: "email"|"chat"|"web"|"api" }` (default `web`; blank subject/body → 422) → **201** `Ticket` with status `new`, no category/severity (the workflow sets those). Also creates the first `ticket_messages` row (role `customer`); does **not** start the workflow. **404** `Customer not found`. *(Implemented, Phase 4)* |
| GET | `/tickets/{id}` | `TicketDetail`. `{id}` is the UUID **or** the ticket number (`CD-1001`). **404** `Ticket not found`. `workflow` is `null` until the ticket has been run. *(Implemented, Phase 4; filled in Phase 10)* |
| POST | `/tickets/{id}/run` | starts the LangGraph workflow (background task). **202** `{ workflow_id, status:"running" }`. **409** `Ticket is waiting on approval` when the ticket is `waiting_on_approval`, **409** `A workflow is already running for this ticket` when a run is in progress. **404** `Ticket not found`. Role `agent`/`admin`. *(Implemented, Phase 10)* |
| GET | `/tickets/{id}/workflow` | `WorkflowState` (latest run). **404** `No workflow has run for this ticket`. Also embedded as `TicketDetail.workflow`. *(Implemented, Phase 10)* |
| GET | `/tickets/{id}/events` | `WorkflowEvent[]` (node transitions, tool calls, timings); `[]` until a workflow has run. *(Implemented, Phase 4)* |
| POST | `/tickets/{id}/reply` | body `{ body: string, internal?: boolean }` → **201** `TicketMessage` (role `agent`, author = caller's name). A public reply moves a `new` ticket to `in_progress`. **409** for a public reply on a `closed` ticket (internal notes still allowed). *(Implemented, Phase 4. Output validation, N5, joins in Phase 7.)* |
| POST | `/tickets/{id}/request-info` | body `{ questions: string[] }` (1-10, blanks dropped) → **201** `TicketMessage` (numbered list) and ticket status `waiting_on_customer`. **409** when closed. *(Implemented, Phase 4)* |
| POST | `/tickets/{id}/escalate` | body `{ reason, priority?: "normal"|"urgent" }` → **201** `Escalation` (team `support_leads`; severity `high`, or `critical` when urgent). Ticket status becomes `escalated`. *(Implemented, Phase 4 as a manual escalation; the AI path is Phase 11.)* |
| PATCH | `/tickets/{id}` | body `{ status?, severity?, assigned_to? }` → `Ticket`. Only sent fields change; `assigned_to: null` un-assigns. Empty body → 422; unknown assignee → 404. Moving to `resolved`/`closed` stamps `resolved_at`. *(Implemented, Phase 4)* |

Mutating ticket routes (`POST /tickets`, `/run`, `/reply`, `/request-info`, `/escalate`, and `PATCH`) require role `agent` or `admin`. A `viewer` receives **403**.

Types:
```ts
type TicketStatus = "new"|"in_progress"|"waiting_on_customer"|"waiting_on_approval"|"escalated"|"resolved"|"closed";
type Severity = "low"|"medium"|"high"|"critical";
type Category = "login_issue"|"billing"|"api_failure"|"workspace_permissions"|"storage_quota"|"integration"|"feature_request"|"account"|"security"|"other";

`/run` and `/workflow` are built (Phase 10). Until Phase 11 a run never pauses: approval-required actions are recorded as `pending_approval` and not executed, and `escalation_required` is reported but no escalation row is filed.

TicketSummary = { id, ticket_number, subject, status, severity, category, customer_id, customer_name, channel, created_at, updated_at, escalation_required:boolean, approval_status: "not_required"|"pending"|"approved"|"rejected" }
Ticket = TicketSummary & { body, assigned_to?, resolved_at?, tags: string[] }
TicketMessage = { id, ticket_id, role: "customer"|"agent"|"system", author_name, body, internal:boolean, attachments: {name,url,size}[] /* always [] in v1 */, created_at }
TicketDetail = Ticket & { messages: TicketMessage[], customer: Customer, subscription: Subscription|null, workspaces: Workspace[], history: TicketSummary[] /* customer's other tickets, max 10 */, workflow: WorkflowState|null, resolution_actions: ResolutionAction[], escalation: Escalation|null /* latest */ }

`escalation_required` is true when an escalation row exists or the status is `escalated`. `approval_status` is the latest approval request's status, else `not_required`. `tags` is always `[]` in v1.
```

## Workflow state (what the right-hand panel renders)
```ts
WorkflowState = {
  workflow_id, ticket_id, status: "running"|"waiting_for_approval"|"completed"|"failed"|"escalated",
  current_node: string|null,
  completed_nodes: string[],            // ordered e.g. ["understand_ticket","classify_severity",...]
  classification: { category: Category, intent: string, summary: string, confidence: number } | null,
  severity: Severity | null,
  severity_reason: string | null,
  customer_context: { customer: Customer, subscription: Subscription|null, workspace: Workspace|null, previous_tickets: TicketSummary[], memory_notes: string[] } | null,
  retrieved_docs: Evidence[],           // { id, title, source, snippet, score, url?, article_id? }
  previous_cases: { ticket_number, subject, resolution_summary, similarity }[],
  diagnosis: { problem: string, probable_causes: string[], troubleshooting_steps: string[], confidence: number } | null,
  resolution_plan: { summary: string, customer_response: string, internal_notes: string, actions: PlannedAction[] } | null,
  actions: ResolutionAction[],          // executed / pending actions
  risk: { level: "low"|"medium"|"high", reasons: string[] } | null,
  escalation_required: boolean,
  escalation_reason: string|null,
  approval_status: "not_required"|"pending"|"approved"|"rejected",
  approval_request_id: string|null,
  final_response: string|null,
  ticket_summary: string|null,
  errors: string[],
  started_at, finished_at?, duration_ms?, token_usage: { prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd }
}
PlannedAction = { tool: string, arguments: object, requires_approval: boolean, description: string }
ResolutionAction = { id, ticket_id, tool, arguments: object, status: "planned"|"pending_approval"|"approved"|"executed"|"rejected"|"failed", result: object|null, requires_approval, created_at, executed_at? }
WorkflowEvent = { id, workflow_id, ticket_id, event_type: "node_started"|"node_completed"|"tool_called"|"llm_called"|"approval_requested"|"approval_resolved"|"error"|"workflow_completed", node: string|null, tool: string|null, message: string, duration_ms: number|null, payload: object, created_at }
```

## Approvals (human-in-the-loop)
| Method | Path | Notes |
|---|---|---|
| GET | `/approvals?status=pending` | `ApprovalRequest[]` |
| GET | `/approvals/{id}` | `ApprovalRequest` |
| POST | `/approvals/{id}/approve` | body `{ note?: string }` → resumes the paused workflow; returns `{ approval: ApprovalRequest, workflow: WorkflowState }` (role `admin` or `agent`). **409** when the run is not paused |
| POST | `/approvals/{id}/reject` | body `{ note?: string }` → resumes workflow on the rejection branch (escalates). **409** when the run is not paused. A `viewer` receives **403** on approve and reject |

`ApprovalRequest = { id, ticket_id, ticket_number, workflow_id, action: PlannedAction, risk_level, reason, requested_by: "ai", status: "pending"|"approved"|"rejected", decided_by?, decision_note?, created_at, decided_at? }`

## Customers
| Method | Path |
|---|---|
| GET | `/customers?search=&page=1&page_size=20` → `{items: Customer[], total, page, page_size}`. Sorted by name; `search` matches name, company or email. Same paging limits as tickets. *(Implemented, Phase 4)* |
| GET | `/customers/{id}` → `CustomerDetail = Customer & { subscription, workspaces: Workspace[], tickets: TicketSummary[] /* max 50, newest first */, memory: CustomerMemory[] /* max 10 */ }`. **404** `Customer not found`. *(Implemented, Phase 4)* |

Customer routes and the read ticket routes need role `viewer` or higher; there is no customer write API in v1.

```ts
Customer = { id, name, email, company, plan: "free"|"pro"|"business"|"enterprise", status, timezone, created_at }
Subscription = { id, customer_id, plan, status, billing_cycle, seats_purchased, seats_used, seat_price, currency, storage_limit_gb, storage_used_gb, api_rate_limit_per_minute, renews_at? }
Workspace = { id, customer_id, name, slug, region, member_count, storage_used_gb, sso_enabled, mfa_required, external_sharing }
CustomerMemory = { id, customer_id, kind: "preference"|"past_issue"|"troubleshooting"|"note", content, source_ticket_id?, created_at }
```

## Knowledge base
| Method | Path |
|---|---|
| GET | `/knowledge/articles?search=&category=` → `Article[]` (title-sorted; `search` matches title, slug or summary; unknown `category` is **422**). Viewer+. *(Implemented, Phase 5)* |
| GET | `/knowledge/articles/{id}` → `Article & { content }`. `{id}` is the UUID **or** the slug. **404** `Article not found`. Viewer+. *(Implemented, Phase 5)* |
| POST | `/knowledge/search` body `{ query (1-500 chars), top_k?: 5 (1-20), mode?: "hybrid"|"semantic"|"keyword", category?: Category }` → `{ results: Evidence[], mode, took_ms }`. One result per article, best first. `category` is a hard filter. Viewer+. *(Implemented, Phase 5)* |
| POST | `/knowledge/reindex` (admin only; agent/viewer **403**) → `{ indexed: number /* chunks */, articles: number }`. Recreates the collection from `support_articles`. *(Implemented, Phase 5)* |

`Evidence = { id /* chunk id */, title, source /* kb://slug#section */, snippet, score, url /* /knowledge/<article id> */, article_id }`. `score` is a fused rank score for ordering, not a probability.

`Article = { id, slug, title, category, tags: string[], summary, updated_at }`

## Escalations
| Method | Path |
|---|---|
| GET | `/escalations?status=` → `Escalation[]` |
| PATCH | `/escalations/{id}` body `{ status: "open"|"acknowledged"|"resolved", note? }` |

`Escalation = { id, ticket_id, team, reason, severity, status: "open"|"acknowledged"|"closed", created_at }`

## Agents (observability page)
`GET /agents` → `{ agents: AgentInfo[], graph: { nodes: {id,label}[], edges: {source,target,label?}[] }, recent_runs: WorkflowState[], stats: { runs_total, runs_completed, runs_failed, avg_duration_ms, total_tokens, total_estimated_cost_usd } }`
`AgentInfo = { name, role, description, tools: string[], last_run_at?, runs: number, avg_duration_ms: number }`

## Audit
`GET /audit?page=&page_size=&actor=&action=` → `{ items: AuditLog[], total }`
`AuditLog = { id, actor, actor_type: "user"|"agent"|"system", action, resource_type, resource_id, details: object, request_id, created_at }`

## Settings
`GET /settings` → `{ demo_mode, environment, llm: {llm_provider, llm_model, embedding_provider, embedding_model, api_key_configured, tracing}, vector_store, redis: "real"|"fake", database: "sqlite"|"postgres", approval_policy: { refunds_require_approval, max_refund_without_approval, approval_required_tools: string[] } }`
`GET /mcp/tools` → `{ tools: {name, description, requires_approval}[] }` (MCP server introspection, optional)


## Contract changes in Phase 4
The Customer, Subscription, Workspace, CustomerMemory, Escalation and TicketMessage shapes now match the database model (`backend/app/models/entities.py`) instead of the first draft: `plan_name`, `region`, `lifetime_value`, `mrr` on Customer/Subscription, `priority`/`assigned_team`/`created_by` on Escalation and the `ai` message role were dropped or renamed. `CustomerDetail` and `TicketDetail` return `workspaces` (a list) because a customer can own several. Response models live in `backend/app/schemas/{records,tickets,customers}.py`; `frontend/lib/types.ts` will copy them in Phase 12.
