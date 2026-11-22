import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { ApprovalBar } from "@/components/ticket/ApprovalBar";
import { ReplyComposer } from "@/components/ticket/ReplyComposer";
import { WorkflowSteps, deriveSteps } from "@/components/ticket/WorkflowSteps";
import { TOKEN_KEY, api } from "@/lib/api";
import type { WorkflowState } from "@/lib/types";
import { WORKFLOW_STEPS, canDecide, shouldPoll } from "@/lib/workflow";

const BASE: WorkflowState = {
  workflow_id: "w1",
  ticket_id: "t1",
  status: "running",
  current_node: null,
  completed_nodes: [],
  classification: null,
  severity: null,
  severity_reason: null,
  retrieved_docs: [],
  previous_cases: [],
  diagnosis: null,
  resolution_plan: null,
  actions: [],
  risk: null,
  escalation_required: false,
  escalation_reason: null,
  approval_status: "not_required",
  approval_request_id: null,
  final_response: null,
  ticket_summary: null,
  errors: [],
};
const wf = (over: Partial<WorkflowState>): WorkflowState => ({ ...BASE, ...over });
const states = (w: WorkflowState | null) => Object.fromEntries(deriveSteps(w).map((s) => [s.id, s.state]));

describe("deriveSteps", () => {
  it("has the twelve graph nodes in order", () => {
    expect(WORKFLOW_STEPS).toHaveLength(12);
    expect(WORKFLOW_STEPS[0].id).toBe("understand_ticket");
    expect(WORKFLOW_STEPS[11].id).toBe("memory_update");
  });

  it("everything is pending before a run", () => {
    expect(new Set(Object.values(states(null)))).toEqual(new Set(["pending"]));
  });

  it("marks completed nodes done and the current node running", () => {
    const s = states(wf({ completed_nodes: ["understand_ticket"], current_node: "classify_severity" }));
    expect(s.understand_ticket).toBe("done");
    expect(s.classify_severity).toBe("current");
    expect(s.customer_context).toBe("pending");
  });

  it("shows the human step as waiting while paused for approval", () => {
    const s = states(
      wf({
        status: "waiting_for_approval",
        current_node: "human_approval",
        completed_nodes: ["understand_ticket", "classify_severity", "customer_context", "knowledge_retrieval", "troubleshooting", "resolution_planning", "risk_check"],
      }),
    );
    expect(s.human_approval).toBe("waiting");
    expect(s.execute_resolution).toBe("pending");
  });

  it("skips the branch that was not taken once the run has finished", () => {
    const s = states(
      wf({
        status: "completed",
        completed_nodes: WORKFLOW_STEPS.map((x) => x.id).filter((n) => n !== "human_approval" && n !== "escalation"),
      }),
    );
    expect(s.human_approval).toBe("skipped");
    expect(s.escalation).toBe("skipped");
    expect(s.execute_resolution).toBe("done");
  });

  it("marks the failing node failed", () => {
    expect(states(wf({ status: "failed", current_node: "troubleshooting" })).troubleshooting).toBe("failed");
  });

  it("renders twelve rows with their state", () => {
    render(<WorkflowSteps workflow={wf({ current_node: "understand_ticket" })} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    expect(screen.getByTestId("step-understand_ticket")).toHaveAttribute("data-state", "current");
  });
});

describe("polling and approval rules", () => {
  it("polls while running, or while a started run has no state yet; not when paused or done", () => {
    expect(shouldPoll(wf({ status: "running" }), true)).toBe(true);
    expect(shouldPoll(null, true)).toBe(true);
    expect(shouldPoll(null, false)).toBe(false);
    expect(shouldPoll(wf({ status: "waiting_for_approval" }), true)).toBe(false);
    expect(shouldPoll(wf({ status: "completed" }), true)).toBe(false);
  });

  it("canDecide needs a pending approval with an id", () => {
    expect(canDecide(wf({ approval_status: "pending", approval_request_id: "a1" }))).toBe(true);
    expect(canDecide(wf({ approval_status: "approved", approval_request_id: "a1" }))).toBe(false);
    expect(canDecide(wf({ approval_status: "pending", approval_request_id: null }))).toBe(false);
    expect(canDecide(null)).toBe(false);
  });
});

describe("ApprovalBar", () => {
  const actions = [{ tool: "create_refund_request", arguments: {}, requires_approval: true, description: "Refund 3 seats" }];
  const pending = wf({ status: "waiting_for_approval", approval_status: "pending", approval_request_id: "a1" });
  const props = { actions, busy: false, onApprove: vi.fn(), onReject: vi.fn() };

  it("renders Approve and Reject only when pending", () => {
    const { rerender } = render(<ApprovalBar {...props} workflow={pending} allowed />);
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
    rerender(<ApprovalBar {...props} workflow={wf({ approval_status: "approved", approval_request_id: "a1" })} allowed />);
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    rerender(<ApprovalBar {...props} workflow={wf({ approval_status: "not_required" })} allowed />);
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("disables both buttons for a viewer", () => {
    render(<ApprovalBar {...props} workflow={pending} allowed={false} />);
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  });

  it("calls the handlers", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(<ApprovalBar {...props} onApprove={onApprove} onReject={onReject} workflow={pending} allowed />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onApprove).toHaveBeenCalledOnce();
    expect(onReject).toHaveBeenCalledOnce();
  });
});

describe("ReplyComposer", () => {
  const handlers = { onDraftChange: vi.fn(), onSend: vi.fn(), onRequestInfo: vi.fn(), onEscalate: vi.fn() };

  it("renders every action disabled for a viewer", () => {
    render(<ReplyComposer {...handlers} draft="Hello" allowed={false} busy={false} />);
    expect(screen.getByLabelText("Reply text")).toBeDisabled();
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });

  it("send is disabled for an empty draft and sends an edited draft for an agent", () => {
    const onSend = vi.fn();
    const { rerender } = render(<ReplyComposer {...handlers} draft="  " allowed busy={false} />);
    expect(screen.getByRole("button", { name: "Send reply" })).toBeDisabled();
    rerender(<ReplyComposer {...handlers} onSend={onSend} draft="Hi there" allowed busy={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Send reply" }));
    expect(onSend).toHaveBeenCalledWith(false);
  });
});

describe("workflow API calls", () => {
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  beforeEach(() => window.localStorage.setItem(TOKEN_KEY, "tok"));
  afterEach(() => vi.unstubAllGlobals());

  it("run is a POST and is never retried", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("down"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.runWorkflow("CD-1002")).rejects.toMatchObject({ name: "NetworkError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/tickets/CD-1002/run");
  });

  it("approve posts to the approval route with the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { approval: {}, workflow: null }));
    vi.stubGlobal("fetch", fetchMock);
    await api.approve("a1", "ok");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/approvals/a1/approve");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ note: "ok" });
  });

  it("a 409 on a second approve click surfaces the server message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(409, { detail: "Approval has already been decided" })));
    await expect(api.approve("a1")).rejects.toMatchObject({ status: 409, detail: "Approval has already been decided" });
  });
});
