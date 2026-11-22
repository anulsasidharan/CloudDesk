// Pure logic for the right-hand workflow panel. No React, so it is easy to test.
import type { WorkflowState } from "./types";

export interface StepDef {
  id: string;
  label: string;
  /** Only runs on one branch of the graph; shown as "skipped" when the run ends without it. */
  optional?: boolean;
}

/** The twelve graph nodes in display order. Ids match `agents/graph.py` NODES. */
export const WORKFLOW_STEPS: StepDef[] = [
  { id: "understand_ticket", label: "Understand" },
  { id: "classify_severity", label: "Classify severity" },
  { id: "customer_context", label: "Customer context" },
  { id: "knowledge_retrieval", label: "Find evidence" },
  { id: "troubleshooting", label: "Troubleshoot" },
  { id: "resolution_planning", label: "Plan resolution" },
  { id: "risk_check", label: "Risk check" },
  { id: "human_approval", label: "Human approval", optional: true },
  { id: "execute_resolution", label: "Execute actions", optional: true },
  { id: "escalation", label: "Escalate", optional: true },
  { id: "ticket_summary", label: "Summarise" },
  { id: "memory_update", label: "Update memory" },
];

export type StepState = "done" | "current" | "waiting" | "pending" | "skipped" | "failed";

export interface DerivedStep extends StepDef {
  state: StepState;
}

const FINISHED = new Set(["completed", "failed", "escalated"]);

/**
 * Work out what to draw for each of the twelve steps.
 * - completed nodes are "done"
 * - while running, the current node is "current"; while paused for a human it is "waiting"
 * - once the run has finished, a step that never ran is "skipped" (the other branch), or "failed"
 *   when the run failed on it. Before a run exists everything is "pending".
 */
export function deriveSteps(workflow: WorkflowState | null | undefined): DerivedStep[] {
  const done = new Set(workflow?.completed_nodes ?? []);
  const finished = !!workflow && FINISHED.has(workflow.status);
  return WORKFLOW_STEPS.map((step) => {
    let state: StepState = "pending";
    if (done.has(step.id)) state = "done";
    else if (workflow && workflow.current_node === step.id) {
      if (workflow.status === "waiting_for_approval") state = "waiting";
      else if (workflow.status === "failed") state = "failed";
      else if (!finished) state = "current";
    } else if (finished) state = "skipped";
    return { ...step, state };
  });
}

/** True while the screen should keep polling /workflow. A paused run does not change by itself. */
export function shouldPoll(workflow: WorkflowState | null | undefined, started: boolean): boolean {
  if (!workflow) return started;
  return workflow.status === "running";
}

/** Approve and Reject show only for a pending approval that belongs to a paused run. */
export function canDecide(workflow: WorkflowState | null | undefined): boolean {
  return !!workflow && workflow.approval_status === "pending" && !!workflow.approval_request_id;
}
