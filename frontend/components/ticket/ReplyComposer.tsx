"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/**
 * The reply box. The AI draft is a suggestion: the agent can edit it before sending.
 * Also hosts the two other human actions: request more info and escalate.
 */
export function ReplyComposer({
  draft,
  onDraftChange,
  allowed,
  busy,
  onSend,
  onRequestInfo,
  onEscalate,
}: {
  draft: string;
  onDraftChange: (value: string) => void;
  allowed: boolean;
  busy: boolean;
  onSend: (internal: boolean) => void;
  onRequestInfo: (questions: string[]) => void;
  onEscalate: (reason: string) => void;
}) {
  const [internal, setInternal] = useState(false);
  const empty = draft.trim() === "";

  return (
    <Card title="Reply">
      <textarea
        aria-label="Reply text"
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        disabled={!allowed}
        rows={6}
        className="w-full rounded border border-slate-300 p-2 text-sm disabled:bg-slate-50"
        placeholder="The AI draft appears here after a run. Edit it before sending."
      />
      <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
        <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} disabled={!allowed} />
        Internal note (not visible to the customer)
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => onSend(internal)} disabled={!allowed || busy || empty}>
          {internal ? "Add note" : "Send reply"}
        </Button>
        <Button
          variant="secondary"
          disabled={!allowed || busy || empty}
          onClick={() =>
            onRequestInfo(
              draft
                .split("\n")
                .map((l) => l.trim())
                .filter(Boolean),
            )
          }
        >
          Request info (one question per line)
        </Button>
        <Button variant="danger" disabled={!allowed || busy || empty} onClick={() => onEscalate(draft.trim())}>
          Escalate (text is the reason)
        </Button>
      </div>
    </Card>
  );
}
