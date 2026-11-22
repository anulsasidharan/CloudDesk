import type { Role } from "./types";

/** "waiting_on_approval" -> "Waiting on approval". */
export function humanize(value: string | null | undefined): string {
  if (!value) return "-";
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "-";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Roles ordered like backend `require_role`: viewer 1 < agent 2 < admin 3. */
export const ROLE_RANK: Record<Role, number> = { viewer: 1, agent: 2, admin: 3 };

export function hasRole(role: Role | undefined, minimum: Role): boolean {
  return !!role && ROLE_RANK[role] >= ROLE_RANK[minimum];
}

/** Viewers read; agents and admins act. Used to disable action buttons. */
export function canAct(role: Role | undefined): boolean {
  return hasRole(role, "agent");
}
