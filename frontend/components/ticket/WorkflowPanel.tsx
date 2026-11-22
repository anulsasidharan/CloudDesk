import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { humanize } from "@/lib/format";
import type { WorkflowState } from "@/lib/types";
import { WorkflowSteps } from "./WorkflowSteps";

/** Right-hand column: steps, chips, evidence, diagnosis and the planned actions. */
export function WorkflowPanel({ workflow }: { workflow: WorkflowState | null }) {
  return (
    <div className="space-y-4">
      <Card title="AI workflow">
        {!workflow && <p className="mb-3 text-sm text-slate-500">Not run yet. Press &quot;Run AI workflow&quot;.</p>}
        {workflow && (
          <div className="mb-3 flex flex-wrap gap-1.5" data-testid="workflow-chips">
            <StatusPill value={workflow.status} />
            {workflow.classification && <StatusPill value={workflow.classification.category} />}
            {workflow.severity && <StatusPill value={workflow.severity} />}
            {workflow.risk && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">Risk: {humanize(workflow.risk.level)}</span>
            )}
            {workflow.approval_status !== "not_required" && <StatusPill value={workflow.approval_status} />}
            {workflow.escalation_required && <StatusPill value="escalated" />}
          </div>
        )}
        <WorkflowSteps workflow={workflow} />
        {workflow?.errors.length ? (
          <ul role="alert" className="mt-3 rounded bg-red-50 p-2 text-xs text-red-800">
            {workflow.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}
      </Card>

      {workflow?.classification && (
        <Card title="Understanding">
          <p className="text-sm">{workflow.classification.summary}</p>
          {workflow.severity_reason && <p className="mt-1 text-xs text-slate-500">{workflow.severity_reason}</p>}
        </Card>
      )}

      {!!workflow?.retrieved_docs.length && (
        <Card title="Evidence">
          <ul className="space-y-2">
            {workflow.retrieved_docs.map((d) => (
              <li key={d.id} className="text-sm">
                <div className="font-medium">{d.title}</div>
                <div className="text-xs text-slate-500">
                  {d.source} - score {d.score.toFixed(2)}
                </div>
                <p className="mt-0.5 text-xs text-slate-600">{d.snippet}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {workflow?.diagnosis && (
        <Card title="Diagnosis">
          <p className="text-sm">{workflow.diagnosis.problem}</p>
          <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
            {workflow.diagnosis.probable_causes.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
          <ol className="mt-2 list-decimal pl-5 text-sm">
            {workflow.diagnosis.troubleshooting_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </Card>
      )}

      {!!workflow?.resolution_plan?.actions.length && (
        <Card title="Planned actions">
          <ul className="space-y-2">
            {workflow.resolution_plan.actions.map((a, i) => {
              const executed = workflow.actions.find((x) => x.tool === a.tool);
              return (
                <li key={i} className="text-sm">
                  <span className="font-mono text-xs">{a.tool}</span>
                  {a.requires_approval && (
                    <span className="ml-2 rounded bg-purple-100 px-1.5 text-xs text-purple-800">needs approval</span>
                  )}
                  {executed && <span className="ml-2 text-xs text-slate-500">{humanize(executed.status)}</span>}
                  <p className="text-xs text-slate-600">{a.description}</p>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
