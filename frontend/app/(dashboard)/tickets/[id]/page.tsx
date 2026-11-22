"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { formatDate, humanize } from "@/lib/format";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { StatusPill } from "@/components/ui/StatusPill";

/**
 * Phase 12: a READ-ONLY ticket view, so list pages have somewhere to link.
 * The three-column workflow screen with actions is Phase 13 (P13-1 to P13-3).
 */
export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: t, error, loading, reload } = useAsync(() => api.ticket(id), [id]);

  return (
    <DataState loading={loading} error={error} onRetry={reload}>
      {t && (
        <>
          <PageHeader
            title={`${t.ticket_number}: ${t.subject}`}
            subtitle={`${humanize(t.channel)} ticket opened ${formatDate(t.created_at)}`}
            right={
              <div className="flex gap-2">
                <StatusPill value={t.status} />
                <StatusPill value={t.severity} />
              </div>
            }
          />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Conversation" className="lg:col-span-2">
              <ul className="space-y-3">
                {t.messages.map((m) => (
                  <li key={m.id} className="rounded border border-slate-100 bg-slate-50 p-3 text-sm">
                    <div className="mb-1 text-xs text-slate-500">
                      {m.author_name} ({m.role}){m.internal ? " - internal note" : ""} - {formatDate(m.created_at)}
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-slate-500">
                Running the AI workflow and approving actions arrive with the ticket workflow screen (Phase 13).
              </p>
            </Card>
            <Card title="Customer">
              <p className="font-medium">
                <Link className="text-brand underline" href={`/customers/${t.customer.id}`}>{t.customer.name}</Link>
              </p>
              <p className="text-sm text-slate-600">{t.customer.company}</p>
              <p className="mt-2 text-sm">Plan: {humanize(t.customer.plan)}</p>
              {t.subscription && (
                <p className="text-sm">
                  Seats: {t.subscription.seats_used} used / {t.subscription.seats_purchased} paid
                </p>
              )}
              <p className="mt-2 text-sm">Category: {humanize(t.category)}</p>
              <p className="text-sm">Approval: {humanize(t.approval_status)}</p>
              {t.escalation && (
                <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800">
                  Escalated to {humanize(t.escalation.team)}: {t.escalation.reason}
                </p>
              )}
            </Card>
          </div>
        </>
      )}
    </DataState>
  );
}
