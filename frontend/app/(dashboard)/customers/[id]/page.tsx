"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { formatDate, humanize } from "@/lib/format";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Td } from "@/components/ui/Table";

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading, reload } = useAsync(() => api.customer(id), [id]);

  return (
    <DataState loading={loading} error={error} onRetry={reload}>
      {c && (
        <>
          <PageHeader title={c.name} subtitle={`${c.company} - ${c.email}`} right={<StatusPill value={c.status} />} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Subscription">
              {c.subscription ? (
                <dl className="space-y-1 text-sm">
                  <div>Plan: {humanize(c.subscription.plan)}</div>
                  <div>Seats: {c.subscription.seats_used} used / {c.subscription.seats_purchased} paid</div>
                  <div>Storage: {c.subscription.storage_used_gb} / {c.subscription.storage_limit_gb} GB</div>
                  <div>API limit: {c.subscription.api_rate_limit_per_minute} per minute</div>
                  <div>Renews: {formatDate(c.subscription.renews_at)}</div>
                </dl>
              ) : (
                <p className="text-sm text-slate-500">No subscription on file.</p>
              )}
            </Card>
            <Card title="Workspaces">
              {c.workspaces.length === 0 ? (
                <p className="text-sm text-slate-500">None.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {c.workspaces.map((w) => (
                    <li key={w.id}>
                      <span className="font-medium">{w.name}</span> ({w.region}), {w.member_count} members
                      {w.sso_enabled ? ", SSO" : ""}
                      {w.mfa_required ? ", MFA required" : ""}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Memory notes">
              {c.memory.length === 0 ? (
                <p className="text-sm text-slate-500">Nothing remembered yet. Notes appear after a workflow run.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {c.memory.map((m) => (
                    <li key={m.id}>
                      <span className="text-xs uppercase text-slate-500">{humanize(m.kind)}</span>
                      <p>{m.content}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
          <h2 className="mb-2 mt-6 text-sm font-semibold text-slate-700">Tickets</h2>
          {c.tickets.length === 0 ? (
            <EmptyState title="No tickets for this customer" />
          ) : (
            <Table headers={["Ticket", "Subject", "Status", "Severity", "Updated"]}>
              {c.tickets.map((t) => (
                <tr key={t.id}>
                  <Td>
                    <Link className="text-brand underline" href={`/tickets/${t.ticket_number}`}>{t.ticket_number}</Link>
                  </Td>
                  <Td>{t.subject}</Td>
                  <Td><StatusPill value={t.status} /></Td>
                  <Td><StatusPill value={t.severity} /></Td>
                  <Td>{formatDate(t.updated_at)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </>
      )}
    </DataState>
  );
}
