"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { hasRole } from "@/lib/format";
import { useAuth } from "./AuthProvider";
import { NAV_ITEMS } from "./nav";

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) => hasRole(user.role, item.minRole));

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-4">
        <div className="mb-6 text-lg font-bold text-brand">CloudDesk</div>
        <nav className="space-y-1" aria-label="Main">
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "block rounded-md px-3 py-2 text-sm",
                  active ? "bg-brand-soft font-medium text-brand" : "text-slate-700 hover:bg-slate-100",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-slate-200 bg-white px-6 py-3 text-sm">
          <span className="text-slate-600">{user.full_name}</span>
          <span
            data-testid="role-badge"
            className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
          >
            {user.role}
          </span>
          <button onClick={logout} className="text-slate-500 underline">
            Sign out
          </button>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
