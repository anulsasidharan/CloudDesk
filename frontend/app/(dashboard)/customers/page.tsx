"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync, useDebounced } from "@/lib/hooks";
import { humanize } from "@/lib/format";
import { PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pager, Table, Td } from "@/components/ui/Table";

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const { data, error, loading, reload } = useAsync(
    () => api.customers({ search: q, page, page_size: 20 }),
    [q, page],
  );

  return (
    <>
      <PageHeader title="Customers" subtitle="Accounts that write in to support" />
      <input
        aria-label="Search customers"
        placeholder="Search name, company or email"
        className="mb-4 w-72 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && data.items.length === 0 ? (
          <EmptyState title="No customers match" />
        ) : (
          data && (
            <>
              <Table headers={["Name", "Company", "Email", "Plan", "Status"]}>
                {data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50">
                    <Td>
                      <Link className="font-medium text-brand underline" href={`/customers/${c.id}`}>{c.name}</Link>
                    </Td>
                    <Td>{c.company}</Td>
                    <Td>{c.email}</Td>
                    <Td>{humanize(c.plan)}</Td>
                    <Td>{humanize(c.status)}</Td>
                  </tr>
                ))}
              </Table>
              <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
            </>
          )
        )}
      </DataState>
    </>
  );
}
