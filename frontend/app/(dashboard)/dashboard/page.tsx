"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Card, PageHeader, Stat } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Td } from "@/components/ui/Table";
import { formatDate } from "@/lib/format";

export default function DashboardPage() {
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), []);
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Where the queue stands right now" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label="Open tickets" value={data.open_tickets} />
              <Stat label="Resolved today" value={data.resolved_today} />
              <Stat label="Pending approvals" value={data.pending_approvals} />
              <Stat label="Open escalations" value={data.escalations_open} />
            </div>
            <Card title="Recent tickets">
              <Table headers={["Ticket", "Subject", "Status", "Severity", "Updated"]}>
                {data.recent_tickets.map((t) => (
                  <tr key={t.id}>
                    <Td>
                      <Link className="text-brand underline" href={`/tickets/${t.ticket_number}`}>
                        {t.ticket_number}
                      </Link>
                    </Td>
                    <Td>{t.subject}</Td>
                    <Td>
                      <StatusPill value={t.status} />
                    </Td>
                    <Td>
                      <StatusPill value={t.severity} />
                    </Td>
                    <Td>{formatDate(t.updated_at)}</Td>
                  </tr>
                ))}
              </Table>
            </Card>
          </div>
        )}
      </DataState>
    </>
  );
}
