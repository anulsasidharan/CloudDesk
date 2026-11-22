"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pager, Table, Td } from "@/components/ui/Table";

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useAsync(() => api.audit({ page, page_size: 50 }), [page]);
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every state-changing request, who made it, and its request id" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && data.items.length === 0 ? (
          <EmptyState title="No audit entries yet" />
        ) : (
          data && (
            <>
              <Table headers={["When", "Actor", "Action", "Resource", "Request id"]}>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <Td>{formatDate(a.created_at)}</Td>
                    <Td>{a.actor} ({a.actor_type})</Td>
                    <Td>{a.action}</Td>
                    <Td>{a.resource_type} {a.resource_id}</Td>
                    <Td className="font-mono text-xs">{a.request_id}</Td>
                  </tr>
                ))}
              </Table>
              <Pager page={page} pageSize={50} total={data.total} onPage={setPage} />
            </>
          )
        )}
      </DataState>
    </>
  );
}
