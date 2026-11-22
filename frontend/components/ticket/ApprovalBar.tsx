"use client";

import { Button } from "@/components/ui/Button";
import { canDecide } from "@/lib/workflow";
import type { PlannedAction, WorkflowState } from "@/lib/types";

/**
 * Approve / Reject. Renders ONLY while the approval is pending (CLAUDE.md section 11),
 * and the buttons are disabled for a viewer. The backend enforces the role as well (403).
 */
export function ApprovalBar({
  workflow,
  actions,
  allowed,
  busy,
  onApprove,
  onReject,
}: {
  workflow: WorkflowState | null;
  actions: PlannedAction[];
  allowed: boolean;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  if (!canDecide(workflow)) return null;
  return (
    <div
      role="region"
      aria-label="Approval required"
      className="rounded-lg border border-purple-200 bg-purple-50 p-4"
    >
      <h2 className="text-sm font-semibold text-purple-900">Approval required</h2>
      <ul className="mt-1 text-sm text-purple-900">
        {actions
          .filter((a) => a.requires_approval)
          .map((a, i) => (
            <li key={i}>{a.description || a.tool}</li>
          ))}
      </ul>
      {workflow?.risk?.reasons.length ? (
        <p className="mt-1 text-xs text-purple-800">Why: {workflow.risk.reasons.join("; ")}</p>
      ) : null}
      <div className="mt-3 flex gap-2">
        <Button onClick={onApprove} disabled={!allowed || busy}>
          Approve
        </Button>
        <Button variant="danger" onClick={onReject} disabled={!allowed || busy}>
          Reject
        </Button>
      </div>
      {!allowed && <p className="mt-2 text-xs text-purple-800">Viewers can read but not decide.</p>}
    </div>
  );
}
