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
| POST | `/auth/demo-login` | `{email?: string, role?: "admin"|"agent"|"viewer"}` | `{access_token, token_type:"bearer", user: User}` (only when `DEMO_MODE=true`) |
| GET | `/auth/me` | – | `User` |

`User = { id, email, full_name, role, avatar_url? }`

## Dashboard
`GET /dashboard/summary` → `{ open_tickets, resolved_today, pending_approvals, escalations_open, avg_resolution_minutes, by_severity:{low,medium,high,critical}, by_category:{[category]:number}, recent_tickets: TicketSummary[], agent_activity: WorkflowEvent[] }`

## Tickets
| Method | Path | Notes |
|---|---|---|
| GET | `/tickets?status=&severity=&search=&page=1&page_size=20` | `{ items: TicketSummary[], total, page, page_size }` |
| POST | `/tickets` | body `{ customer_id, subject, body, channel?: "email"|"chat"|"web"|"api" }` → `Ticket` (also creates first `ticket_messages` row; does **not** start the workflow) |
| GET | `/tickets/{id}` | `TicketDetail` |
| POST | `/tickets/{id}/run` | starts the LangGraph workflow (background task). **202** `{ workflow_id, status:"running" }`. **409** when the ticket is already `waiting_on_approval` |
| GET | `/tickets/{id}/workflow` | `WorkflowState` (latest run) |
| GET | `/tickets/{id}/events` | `WorkflowEvent[]` (node transitions, tool calls, timings) |
| POST | `/tickets/{id}/reply` | body `{ body: string, internal?: boolean }` → `TicketMessage` (sends the final/edited reply; role `agent`) |
| POST | `/tickets/{id}/request-info` | body `{ questions: string[] }` → `TicketMessage` and ticket status `waiting_on_customer` |
| POST | `/tickets/{id}/escalate` | body `{ reason, priority?: "normal"|"urgent" }` → `Escalation` |
| PATCH | `/tickets/{id}` | body `{ status?, severity?, assigned_to? }` → `Ticket` |

Mutating ticket routes (`POST /tickets`, `/run`, `/reply`, `/request-info`, `/escalate`, and `PATCH`) require role `agent` or `admin`. A `viewer` receives **403**.

Types:
```ts
type TicketStatus = "new"|"in_progress"|"waiting_on_customer"|"waiting_on_approval"|"escalated"|"resolved"|"closed";
type Severity = "low"|"medium"|"high"|"critical";
type Category = "login_issue"|"billing"|"api_failure"|"workspace_permissions"|"storage_quota"|"integration"|"feature_request"|"account"|"security"|"other";

TicketSummary = { id, ticket_number, subject, status, severity, category, customer_id, customer_name, channel, created_at, updated_at, escalation_required:boolean, approval_status: "not_required"|"pending"|"approved"|"rejected" }
Ticket = TicketSummary & { body, assigned_to?, resolved_at?, tags: string[] }
TicketMessage = { id, ticket_id, role: "customer"|"agent"|"system"|"ai", author_name, body, internal:boolean, attachments: {name,url,size}[], created_at }
TicketDetail = Ticket & { messages: TicketMessage[], customer: Customer, subscription: Subscription|null, history: TicketSummary[], workflow: WorkflowState|null, resolution_actions: ResolutionAction[], escalation: Escalation|null }
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
| GET | `/customers?search=&page=&page_size=` → `{items: Customer[], total, page, page_size}` |
| GET | `/customers/{id}` → `CustomerDetail = Customer & { subscription, workspace, tickets: TicketSummary[], memory: CustomerMemory[] }` |

```ts
Customer = { id, name, email, company, plan_name, status: "active"|"trial"|"past_due"|"churned", created_at, region, lifetime_value }
Subscription = { id, customer_id, plan: "free"|"pro"|"business"|"enterprise", seats, status, renews_at, mrr, storage_quota_gb, storage_used_gb, api_rate_limit }
Workspace = { id, customer_id, name, member_count, storage_used_gb, integrations: string[], sso_enabled: boolean }
CustomerMemory = { id, customer_id, memory_type: "preference"|"past_issue"|"troubleshooting"|"note", content, source_ticket_id?, created_at }
```

## Knowledge base
| Method | Path |
|---|---|
| GET | `/knowledge/articles?search=&category=` → `Article[]` |
| GET | `/knowledge/articles/{id}` → `Article & { content }` |
| POST | `/knowledge/search` body `{ query, top_k?: 5, mode?: "hybrid"|"semantic"|"keyword" }` → `{ results: Evidence[], mode, took_ms }` |
| POST | `/knowledge/reindex` (admin) → `{ indexed: number }` |

`Article = { id, slug, title, category, tags: string[], summary, updated_at }`

## Escalations
| Method | Path |
|---|---|
| GET | `/escalations?status=` → `Escalation[]` |
| PATCH | `/escalations/{id}` body `{ status: "open"|"acknowledged"|"resolved", note? }` |

`Escalation = { id, ticket_id, ticket_number, reason, priority, status, created_by: "ai"|"human", assigned_team, created_at, resolved_at? }`

## Agents (observability page)
`GET /agents` → `{ agents: AgentInfo[], graph: { nodes: {id,label}[], edges: {source,target,label?}[] }, recent_runs: WorkflowState[], stats: { runs_total, runs_completed, runs_failed, avg_duration_ms, total_tokens, total_estimated_cost_usd } }`
`AgentInfo = { name, role, description, tools: string[], last_run_at?, runs: number, avg_duration_ms: number }`

## Audit
`GET /audit?page=&page_size=&actor=&action=` → `{ items: AuditLog[], total }`
`AuditLog = { id, actor, actor_type: "user"|"agent"|"system", action, resource_type, resource_id, details: object, request_id, created_at }`

## Settings
`GET /settings` → `{ demo_mode, environment, llm: {llm_provider, llm_model, embedding_provider, embedding_model, api_key_configured, tracing}, vector_store, redis: "real"|"fake", database: "sqlite"|"postgres", approval_policy: { refunds_require_approval, max_refund_without_approval, approval_required_tools: string[] } }`
`GET /mcp/tools` → `{ tools: {name, description, requires_approval}[] }` (MCP server introspection, optional)
