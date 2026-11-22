import type { Role } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  /** Lowest role that sees the link (the backend enforces it too). */
  minRole: Role;
}

/** Navigation is declared once; the sidebar and tests both read this list. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", minRole: "viewer" },
  { href: "/tickets", label: "Tickets", minRole: "viewer" },
  { href: "/customers", label: "Customers", minRole: "viewer" },
  { href: "/knowledge", label: "Knowledge", minRole: "viewer" },
  { href: "/escalations", label: "Escalations", minRole: "viewer" },
  { href: "/agents", label: "Agents", minRole: "viewer" },
  { href: "/audit", label: "Audit", minRole: "viewer" },
  { href: "/settings", label: "Settings", minRole: "admin" },
];
