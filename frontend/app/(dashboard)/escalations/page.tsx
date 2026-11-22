"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { formatDate, humanize } from "@/lib/format";
import { PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Td } from "@/components/ui/Table";

export default function EscalationsPage() {
  const { data, error, loading, reload } = useAsync(() => api.escalations(), []);
  return (
    <>
      <PageHeader title="Escalations" subtitle="Cases handed to a specialist team" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && data.length === 0 ? (
          <EmptyState title="No escalations" description="Policy cases and rejected approvals show up here." />
        ) : (
          data && (
            <Table headers={["Team", "Reason", "Severity", "Status", "Created"]}>
              {data.map((e) => (
                <tr key={e.id}>
                  <Td>{humanize(e.team)}</Td>
                  <Td>{e.reason}</Td>
                  <Td><StatusPill value={e.severity} /></Td>
                  <Td><StatusPill value={e.status} /></Td>
                  <Td>{formatDate(e.created_at)}</Td>
                </tr>
              ))}
            </Table>
          )
        )}
      </DataState>
    </>
  );
}
