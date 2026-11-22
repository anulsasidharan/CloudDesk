// The ONLY place the console talks to the backend (CLAUDE.md section 11).
import type {
  AgentsResponse,
  AppSettings,
  ApprovalRequest,
  Article,
  AuditLog,
  CustomerDetail,
  Customer,
  DashboardSummary,
  DecisionResult,
  Escalation,
  Page,
  Role,
  RunAccepted,
  TicketDetail,
  TicketMessage,
  TicketSummary,
  TokenResponse,
  User,
  WorkflowEvent,
  WorkflowState,
} from "./types";

// Inlined at build time: the image is rebuilt per environment.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const TOKEN_KEY = "clouddesk_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/** The server could not be reached at all (down, offline, CORS). */
export class NetworkError extends Error {
  constructor(message = "Cannot reach the CloudDesk API") {
    super(message);
    this.name = "NetworkError";
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: nothing to clear */
  }
}

export function redirectToLogin(reason = "expired"): void {
  window.location.assign(`/login?reason=${reason}`);
}

/** A route that exists in the contract but is not built in the backend yet. */
export function isNotBuilt(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404 && error.detail === "Not Found";
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  /** false for login: a 401 there is a wrong credential, not an expired session. */
  auth?: boolean;
  retries?: number;
  retryDelayMs?: number;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, API_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) return data.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    /* body was not JSON */
  }
  return res.statusText || `HTTP ${res.status}`;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true, retryDelayMs = 400 } = opts;
  // Only idempotent reads are retried; retrying a POST could act twice.
  const retries = opts.retries ?? (method === "GET" ? 2 : 0);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response | undefined;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      res = await fetch(buildUrl(path, query), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      break;
    } catch {
      if (attempt === retries) throw new NetworkError();
      await sleep(retryDelayMs * (attempt + 1));
    }
  }
  if (!res) throw new NetworkError();

  if (res.status === 401 && auth) {
    clearToken();
    redirectToLogin("expired");
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login: (payload: { email?: string; role?: Role }) =>
    request<TokenResponse>("/api/v1/auth/demo-login", { method: "POST", body: payload, auth: false }),
  me: () => request<User>("/api/v1/auth/me"),

  dashboard: () => request<DashboardSummary>("/api/v1/dashboard/summary"),

  tickets: (q: { status?: string; severity?: string; search?: string; page?: number; page_size?: number }) =>
    request<Page<TicketSummary>>("/api/v1/tickets", { query: q }),
  ticket: (id: string) => request<TicketDetail>(`/api/v1/tickets/${encodeURIComponent(id)}`),
  ticketEvents: (id: string) =>
    request<WorkflowEvent[]>(`/api/v1/tickets/${encodeURIComponent(id)}/events`),

  // Phase 13: the ticket workflow screen. Every write is a POST, so it is never auto-retried.
  runWorkflow: (id: string) =>
    request<RunAccepted>(`/api/v1/tickets/${encodeURIComponent(id)}/run`, { method: "POST" }),
  workflow: (id: string) => request<WorkflowState>(`/api/v1/tickets/${encodeURIComponent(id)}/workflow`),
  approve: (approvalId: string, note?: string) =>
    request<DecisionResult>(`/api/v1/approvals/${encodeURIComponent(approvalId)}/approve`, {
      method: "POST",
      body: { note },
    }),
  reject: (approvalId: string, note?: string) =>
    request<DecisionResult>(`/api/v1/approvals/${encodeURIComponent(approvalId)}/reject`, {
      method: "POST",
      body: { note },
    }),
  approval: (approvalId: string) =>
    request<ApprovalRequest>(`/api/v1/approvals/${encodeURIComponent(approvalId)}`),
  reply: (id: string, body: string, internal = false) =>
    request<TicketMessage>(`/api/v1/tickets/${encodeURIComponent(id)}/reply`, {
      method: "POST",
      body: { body, internal },
    }),
  requestInfo: (id: string, questions: string[]) =>
    request<TicketMessage>(`/api/v1/tickets/${encodeURIComponent(id)}/request-info`, {
      method: "POST",
      body: { questions },
    }),
  escalate: (id: string, reason: string, priority: "normal" | "urgent" = "normal") =>
    request<Escalation>(`/api/v1/tickets/${encodeURIComponent(id)}/escalate`, {
      method: "POST",
      body: { reason, priority },
    }),

  customers: (q: { search?: string; page?: number; page_size?: number }) =>
    request<Page<Customer>>("/api/v1/customers", { query: q }),
  customer: (id: string) => request<CustomerDetail>(`/api/v1/customers/${encodeURIComponent(id)}`),

  articles: (q: { search?: string; category?: string }) =>
    request<Article[]>("/api/v1/knowledge/articles", { query: q }),

  escalations: (status?: string) => request<Escalation[]>("/api/v1/escalations", { query: { status } }),
  agents: () => request<AgentsResponse>("/api/v1/agents"),
  audit: (q: { page?: number; page_size?: number; actor?: string; action?: string }) =>
    request<Page<AuditLog>>("/api/v1/audit", { query: q }),
  settings: () => request<AppSettings>("/api/v1/settings"),
};
