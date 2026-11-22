import { cn } from "@/lib/cn";
import type { WorkflowState } from "@/lib/types";
import { deriveSteps, type StepState } from "@/lib/workflow";

export { deriveSteps };

const DOT: Record<StepState, string> = {
  done: "bg-green-500",
  current: "bg-blue-500 animate-pulse",
  waiting: "bg-purple-500 animate-pulse",
  pending: "bg-slate-300",
  skipped: "bg-slate-200",
  failed: "bg-red-500",
};

const LABEL: Record<StepState, string> = {
  done: "Done",
  current: "Running",
  waiting: "Waiting for a human",
  pending: "Pending",
  skipped: "Skipped",
  failed: "Failed",
};

/** The twelve graph steps as a vertical list. Which one is lit comes from deriveSteps(). */
export function WorkflowSteps({ workflow }: { workflow: WorkflowState | null }) {
  const steps = deriveSteps(workflow);
  return (
    <ol className="space-y-1.5" aria-label="Workflow steps">
      {steps.map((s) => (
        <li
          key={s.id}
          data-testid={`step-${s.id}`}
          data-state={s.state}
          className={cn("flex items-center gap-2 text-sm", s.state === "skipped" && "text-slate-400")}
        >
          <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", DOT[s.state])} aria-hidden />
          <span className={cn(s.state === "current" && "font-medium")}>{s.label}</span>
          <span className="ml-auto text-xs text-slate-500">{LABEL[s.state]}</span>
        </li>
      ))}
    </ol>
  );
}
