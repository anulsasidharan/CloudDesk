// Mirrors docs/API_CONTRACT.md and backend/app/schemas/*. Change them together.

export type Role = "viewer" | "agent" | "admin";
export type TicketStatus =
  | "new"
  | "in_progress"
  | "waiting_on_customer"
  | "waiting_on_approval"
  | "escalated"
  | "resolved"
  | "closed";
export type Severity = "low" | "medium" | "high" | "critical";
export type Category =
  | "login_issue"
  | "billing"
  | "api_failure"
  | "workspace_permissions"
  | "storage_quota"
  | "integration"
  | "feature_request"
  | "account"
  | "security"
  | "other";
export type ApprovalState = "not_required" | "pending" | "approved" | "rejected";
export type Plan = "free" | "pro" | "business" | "enterprise";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Customer {
  id: string;
  name: string;
  email: string;
  company: string;
  plan: Plan;
  status: string;
  timezone: string;
  created_at: string;
}

export interface Subscription {
  id: string;
  customer_id: string;
  plan: Plan;
  status: string;
  billing_cycle: string;
  seats_purchased: number;
  seats_used: number;
  seat_price: number;
  currency: string;
  storage_limit_gb: number;
  storage_used_gb: number;
  api_rate_limit_per_minute: number;
  renews_at?: string | null;
}

export interface Workspace {
  id: string;
  customer_id: string;
  name: string;
  slug: string;
  region: string;
  member_count: number;
  storage_used_gb: number;
  sso_enabled: boolean;
  mfa_required: boolean;
  external_sharing: boolean;
}

export interface CustomerMemory {
  id: string;
  customer_id: string;
  kind: "preference" | "past_issue" | "troubleshooting" | "note";
  content: string;
  source_ticket_id?: string | null;
  created_at: string;
}

export interface TicketSummary {
  id: string;
  ticket_number: string;
  subject: string;
  status: TicketStatus;
  severity: Severity | null;
  category: Category | null;
  customer_id: string;
  customer_name: string;
  channel: string;
  created_at: string;
  updated_at: string;
  escalation_required: boolean;
  approval_status: ApprovalState;
}

export interface Ticket extends TicketSummary {
  body: string;
  assigned_to?: string | null;
  resolved_at?: string | null;
  tags: string[];
}

export interface TicketMessage {
  id: string;
  ticket_id: string;
  role: "customer" | "agent" | "system";
  author_name: string;
  body: string;
  internal: boolean;
  created_at: string;
}

export interface Escalation {
  id: string;
  ticket_id: string;
  team: string;
  reason: string;
  severity: string;
  status: "open" | "acknowledged" | "closed";
  created_at: string;
}

export interface TicketDetail extends Ticket {
  messages: TicketMessage[];
  customer: Customer;
  subscription: Subscription | null;
  workspaces: Workspace[];
  history: TicketSummary[];
  workflow: Record<string, unknown> | null;
  escalation: Escalation | null;
}

export interface CustomerDetail extends Customer {
  subscription: Subscription | null;
  workspaces: Workspace[];
  tickets: TicketSummary[];
  memory: CustomerMemory[];
}

export interface Article {
  id: string;
  slug: string;
  title: string;
  category: Category;
  tags: string[];
  summary: string;
  updated_at: string;
}

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  ticket_id: string;
  event_type: string;
  node: string | null;
  tool: string | null;
  message: string;
  duration_ms: number | null;
  created_at: string;
}

// Routes below are in the contract but not built in the backend yet (see docs/API_CONTRACT.md).
export interface DashboardSummary {
  open_tickets: number;
  resolved_today: number;
  pending_approvals: number;
  escalations_open: number;
  avg_resolution_minutes: number;
  by_severity: Record<Severity, number>;
  by_category: Record<string, number>;
  recent_tickets: TicketSummary[];
  agent_activity: WorkflowEvent[];
}

export interface AgentInfo {
  name: string;
  role: string;
  description: string;
  tools: string[];
  runs: number;
  avg_duration_ms: number;
  last_run_at?: string | null;
}

export interface AgentsResponse {
  agents: AgentInfo[];
  graph: {
    nodes: { id: string; label: string }[];
    edges: { source: string; target: string; label?: string }[];
  };
  stats: {
    runs_total: number;
    runs_completed: number;
    runs_failed: number;
    avg_duration_ms: number;
    total_tokens: number;
    total_estimated_cost_usd: number;
  };
}

export interface AuditLog {
  id: string;
  actor: string;
  actor_type: "user" | "agent" | "system";
  action: string;
  resource_type: string;
  resource_id: string;
  request_id: string;
  created_at: string;
}

// ---- Phase 13: workflow and approvals (docs/API_CONTRACT.md "Workflow state", "Approvals") ----

export type WorkflowStatus = "running" | "waiting_for_approval" | "completed" | "failed" | "escalated";

export interface Evidence {
  id: string;
  title: string;
  source: string;
  snippet: string;
  score: number;
  url?: string | null;
  article_id?: string | null;
}

export interface PlannedAction {
  tool: string;
  arguments: Record<string, unknown>;
  requires_approval: boolean;
  description: string;
}

export interface ResolutionAction {
  id: string;
  ticket_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: "planned" | "pending_approval" | "approved" | "executed" | "rejected" | "failed";
  result: Record<string, unknown> | null;
  requires_approval: boolean;
  created_at: string;
  executed_at?: string | null;
}

export interface WorkflowState {
  workflow_id: string;
  ticket_id: string;
  status: WorkflowStatus;
  current_node: string | null;
  completed_nodes: string[];
  classification: { category: Category; intent: string; summary: string; confidence: number } | null;
  severity: Severity | null;
  severity_reason: string | null;
  retrieved_docs: Evidence[];
  previous_cases: { ticket_number: string; subject: string; resolution_summary: string; similarity: number }[];
  diagnosis: {
    problem: string;
    probable_causes: string[];
    troubleshooting_steps: string[];
    confidence: number;
  } | null;
  resolution_plan: {
    summary: string;
    customer_response: string;
    internal_notes: string;
    actions: PlannedAction[];
  } | null;
  actions: ResolutionAction[];
  risk: { level: "low" | "medium" | "high"; reasons: string[] } | null;
  escalation_required: boolean;
  escalation_reason: string | null;
  approval_status: ApprovalState;
  approval_request_id: string | null;
  final_response: string | null;
  ticket_summary: string | null;
  errors: string[];
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  token_usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  } | null;
}

export interface ApprovalRequest {
  id: string;
  ticket_id: string;
  ticket_number: string;
  workflow_id: string;
  action: PlannedAction | null;
  actions: PlannedAction[];
  risk_level: string;
  reason: string;
  requested_by: string;
  status: "pending" | "approved" | "rejected";
  decided_by?: string | null;
  decision_note?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface DecisionResult {
  approval: ApprovalRequest;
  workflow: WorkflowState | null;
}

export interface RunAccepted {
  workflow_id: string;
  status: "running";
}

export interface AppSettings {
  demo_mode: boolean;
  environment: string;
  llm: { llm_provider: string; llm_model: string; api_key_configured: boolean };
  vector_store: string;
  redis: string;
  database: string;
  approval_policy: {
    refunds_require_approval: boolean;
    max_refund_without_approval: number;
    approval_required_tools: string[];
  };
}
