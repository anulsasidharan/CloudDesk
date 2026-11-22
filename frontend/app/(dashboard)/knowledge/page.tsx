"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync, useDebounced } from "@/lib/hooks";
import { humanize } from "@/lib/format";
import { PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, Td } from "@/components/ui/Table";

export default function KnowledgePage() {
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const { data, error, loading, reload } = useAsync(() => api.articles({ search: q }), [q]);

  return (
    <>
      <PageHeader title="Knowledge base" subtitle="The only source for customer-facing policy claims" />
      <input
        aria-label="Search articles"
        placeholder="Search title or summary"
        className="mb-4 w-72 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && data.length === 0 ? (
          <EmptyState title="No articles match" />
        ) : (
          data && (
            <Table headers={["Title", "Category", "Summary", "Tags"]}>
              {data.map((a) => (
                <tr key={a.id}>
                  <Td className="font-medium">{a.title}</Td>
                  <Td>{humanize(a.category)}</Td>
                  <Td>{a.summary}</Td>
                  <Td>{a.tags.join(", ")}</Td>
                </tr>
              ))}
            </Table>
          )
        )}
      </DataState>
    </>
  );
}
