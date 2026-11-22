"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useAsync, usePolling } from "@/lib/hooks";
import { canAct, formatDate, humanize } from "@/lib/format";
import { canDecide, shouldPoll } from "@/lib/workflow";
import type { WorkflowState } from "@/lib/types";
import { useAuth } from "@/components/layout/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataState } from "@/components/ui/DataState";
import { StatusPill } from "@/components/ui/StatusPill";
import { ApprovalBar } from "@/components/ticket/ApprovalBar";
import { ReplyComposer } from "@/components/ticket/ReplyComposer";
import { WorkflowPanel } from "@/components/ticket/WorkflowPanel";

/** Phase 13 (F12): everything an agent does with one ticket, on one screen. */
export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const allowed = canAct(user.role);
  const { data: t, error, loading, reload } = useAsync(() => api.ticket(id), [id]);

  const [wf, setWf] = useState<WorkflowState | null>(null);
  const [started, setStarted] = useState(false);
  const [draft, setDraft] = useState("");
  const draftEdited = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const fail = (err: unknown) =>
    setMessage({ kind: "error", text: err instanceof ApiError ? err.detail : "Something went wrong" });

  // Pick up a run that already exists (404 just means "not run yet").
  useEffect(() => {
    api
      .workflow(id)
      .then(setWf)
      .catch(() => setWf(null));
  }, [id]);

  // Poll every 2 s while a run is in progress. A run paused for approval does not change by itself.
  const refresh = useCallback(async () => {
    try {
      setWf(await api.workflow(id));
    } catch {
      /* keep the last good state; the next tick retries */
    }
  }, [id]);
  usePolling(refresh, 2000, shouldPoll(wf, started));

  // When a run leaves "running", the ticket row (status, messages, approval) has changed: reload it.
  const status = wf?.status;
  useEffect(() => {
    if (status && status !== "running") {
      setStarted(false);
      reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // Prefill the reply box with the AI draft until the agent starts typing.
  const aiDraft = wf?.final_response ?? wf?.resolution_plan?.customer_response ?? "";
  useEffect(() => {
    if (aiDraft && !draftEdited.current) setDraft(aiDraft);
  }, [aiDraft]);

  const act = async (work: () => Promise<void>, okText: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await work();
      setMessage({ kind: "ok", text: okText });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const run = () =>
    act(async () => {
      await api.runWorkflow(id);
      draftEdited.current = false;
      setDraft("");
      setWf(null);
      setStarted(true);
    }, "Workflow started.");

  const decide = (approve: boolean) =>
    act(
      async () => {
        const approvalId = wf?.approval_request_id;
        if (!approvalId) throw new ApiError(409, "No pending approval");
        const result = approve ? await api.approve(approvalId) : await api.reject(approvalId);
        if (result.workflow) setWf(result.workflow);
        reload();
      },
      approve ? "Approved. The action ran once." : "Rejected. The ticket was escalated.",
    );

  const send = (internal: boolean) =>
    act(async () => {
      await api.reply(id, draft.trim(), internal);
      draftEdited.current = false;
      setDraft("");
      reload();
    }, internal ? "Internal note added." : "Reply sent.");

  const running = wf?.status === "running" || (started && !wf);
  const waiting = t?.status === "waiting_on_approval" || wf?.status === "waiting_for_approval";

  return (
    <DataState loading={loading && !t} error={error} onRetry={reload}>
      {t && (
        <>
          <PageHeader
            title={`${t.ticket_number}: ${t.subject}`}
            subtitle={`${humanize(t.channel)} ticket opened ${formatDate(t.created_at)}`}
            right={
              <div className="flex items-center gap-2">
                <StatusPill value={t.status} />
                <StatusPill value={t.severity} />
                <Button onClick={run} disabled={!allowed || busy || running || waiting}>
                  {running ? "Running..." : "Run AI workflow"}
                </Button>
              </div>
            }
          />
          {message && (
            <p
              role={message.kind === "error" ? "alert" : "status"}
              className={
                message.kind === "error"
                  ? "mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800"
                  : "mb-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800"
              }
            >
              {message.text}
            </p>
          )}
          {!allowed && (
            <p className="mb-4 text-xs text-slate-500">You have read-only access. Action buttons are disabled.</p>
          )}

          <div className="grid gap-4 lg:grid-cols-3">
            {/* Left: conversation + composer */}
            <div className="space-y-4">
              <Card title="Conversation">
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
              </Card>
              <ReplyComposer
                draft={draft}
                onDraftChange={(v) => {
                  draftEdited.current = true;
                  setDraft(v);
                }}
                allowed={allowed}
                busy={busy}
                onSend={send}
                onRequestInfo={(qs) =>
                  act(async () => {
                    await api.requestInfo(id, qs);
                    setDraft("");
                    reload();
                  }, "Questions sent to the customer.")
                }
                onEscalate={(reason) =>
                  act(async () => {
                    await api.escalate(id, reason);
                    setDraft("");
                    reload();
                  }, "Escalated to support leads.")
                }
              />
            </div>

            {/* Centre: customer */}
            <Card title="Customer">
              <p className="font-medium">
                <Link className="text-brand underline" href={`/customers/${t.customer.id}`}>
                  {t.customer.name}
                </Link>
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
              {t.history.length > 0 && (
                <div className="mt-3">
                  <h3 className="text-xs font-semibold uppercase text-slate-500">Previous tickets</h3>
                  <ul className="mt-1 space-y-1 text-sm">
                    {t.history.slice(0, 5).map((h) => (
                      <li key={h.id}>
                        <Link className="text-brand underline" href={`/tickets/${h.ticket_number}`}>
                          {h.ticket_number}
                        </Link>{" "}
                        {h.subject}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>

            {/* Right: workflow */}
            <div className="space-y-4">
              <ApprovalBar
                workflow={wf}
                actions={wf?.resolution_plan?.actions ?? []}
                allowed={allowed}
                busy={busy}
                onApprove={() => decide(true)}
                onReject={() => decide(false)}
              />
              <WorkflowPanel workflow={wf} />
              {wf && !canDecide(wf) && wf.ticket_summary && (
                <Card title="Summary">
                  <p className="text-sm">{wf.ticket_summary}</p>
                </Card>
              )}
            </div>
          </div>
        </>
      )}
    </DataState>
  );
}
