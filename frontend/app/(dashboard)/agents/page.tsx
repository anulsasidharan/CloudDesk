"use client";

import { api, } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { formatMs } from "@/lib/format";
import { Card, PageHeader, Stat } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { Table, Td } from "@/components/ui/Table";

export default function AgentsPage() {
  const { data, error, loading, reload } = useAsync(() => api.agents(), []);
  return (
    <>
      <PageHeader title="Agents" subtitle="The specialist team and how the workflow runs" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label="Runs" value={data.stats.runs_total} />
              <Stat label="Completed" value={data.stats.runs_completed} />
              <Stat label="Avg duration" value={formatMs(data.stats.avg_duration_ms)} />
              <Stat label="Tokens" value={data.stats.total_tokens} />
            </div>
            <Table headers={["Agent", "Role", "Tools", "Runs", "Avg duration"]}>
              {data.agents.map((a) => (
                <tr key={a.name}>
                  <Td className="font-medium">{a.name}</Td>
                  <Td>{a.role}</Td>
                  <Td>{a.tools.join(", ") || "-"}</Td>
                  <Td>{a.runs}</Td>
                  <Td>{formatMs(a.avg_duration_ms)}</Td>
                </tr>
              ))}
            </Table>
            <Card title="Workflow steps">
              <p className="text-sm">{data.graph.nodes.map((n) => n.label).join(" > ")}</p>
            </Card>
          </div>
        )}
      </DataState>
    </>
  );
}
