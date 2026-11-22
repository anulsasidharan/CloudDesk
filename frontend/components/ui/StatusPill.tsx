import { cn } from "@/lib/cn";
import { humanize } from "@/lib/format";

const TONES: Record<string, string> = {
  // ticket status
  new: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-800",
  waiting_on_customer: "bg-amber-100 text-amber-800",
  waiting_on_approval: "bg-purple-100 text-purple-800",
  escalated: "bg-red-100 text-red-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-slate-200 text-slate-600",
  // severity
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
  // approvals and escalations
  pending: "bg-purple-100 text-purple-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  open: "bg-red-100 text-red-800",
  acknowledged: "bg-amber-100 text-amber-800",
};

/** A small coloured label for any status-like value. Unknown values render neutral. */
export function StatusPill({ value }: { value: string | null | undefined }) {
  const tone = (value && TONES[value]) || "bg-slate-100 text-slate-700";
  return (
    <span
      data-testid="status-pill"
      className={cn("inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", tone)}
    >
      {humanize(value)}
    </span>
  );
}
