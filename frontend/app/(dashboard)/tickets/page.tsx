"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync, useDebounced } from "@/lib/hooks";
import { formatDate, humanize } from "@/lib/format";
import { PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Pager, Table, Td } from "@/components/ui/Table";

const PAGE_SIZE = 20;
const STATUSES = ["new", "in_progress", "waiting_on_customer", "waiting_on_approval", "escalated", "resolved", "closed"];
const SEVERITIES = ["low", "medium", "high", "critical"];

export default function TicketsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);

  const { data, error, loading, reload } = useAsync(
    () => api.tickets({ search: q, status, severity, page, page_size: PAGE_SIZE }),
    [q, status, severity, page],
  );

  const select = "rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm";
  return (
    <>
      <PageHeader title="Tickets" subtitle="Newest first. Open one to see the customer and the thread." />
      <div className="mb-4 flex flex-wrap gap-2">
        <input
          aria-label="Search tickets"
          placeholder="Search subject, body or CD-1001"
          className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <select aria-label="Status" className={select} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{humanize(s)}</option>
          ))}
        </select>
        <select aria-label="Severity" className={select} value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{humanize(s)}</option>
          ))}
        </select>
      </div>
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && data.items.length === 0 ? (
          <EmptyState title="No tickets match" description="Try clearing the search or filters." />
        ) : (
          data && (
            <>
              <Table headers={["Ticket", "Subject", "Customer", "Category", "Status", "Severity", "Approval", "Updated"]}>
                {data.items.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <Td>
                      <Link className="font-medium text-brand underline" href={`/tickets/${t.ticket_number}`}>
                        {t.ticket_number}
                      </Link>
                    </Td>
                    <Td>{t.subject}</Td>
                    <Td>
                      <Link className="underline" href={`/customers/${t.customer_id}`}>{t.customer_name}</Link>
                    </Td>
                    <Td>{humanize(t.category)}</Td>
                    <Td><StatusPill value={t.status} /></Td>
                    <Td><StatusPill value={t.severity} /></Td>
                    <Td>{t.approval_status === "not_required" ? "-" : <StatusPill value={t.approval_status} />}</Td>
                    <Td>{formatDate(t.updated_at)}</Td>
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
