"use client";

import { useState } from "react";
import { ApiError, approve, reject, retry } from "@/lib/api";
import type { ActionStatus } from "@/lib/types";

interface Props {
  id: number;
  status: ActionStatus;
  error?: string | null;
  /** asked before approving, e.g. "This writes to Google Docs" */
  confirmText?: string;
  approveDisabledReason?: string;
  /** a reply draft's text as shown: approving sends it so a changed draft is never published unseen */
  seenReply?: string;
  /** the Hindi text shown on the card (null when none was shown) */
  seenTranslation?: string | null;
  onDone: () => void;
}

const BADGE: Record<string, string> = {
  pending: "border-state-warn-border bg-state-warn-bg text-state-warn-text",
  approved: "border-state-warn-border bg-state-warn-bg text-state-warn-text",
  executed: "border-state-pass-border bg-state-pass-bg text-state-pass-text",
  failed: "border-state-danger-border bg-state-danger-bg text-state-danger-text",
  rejected: "border-border-strong bg-surface-bg text-text-secondary",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[status] ?? BADGE.rejected}`}>
      {status}
    </span>
  );
}

export function ActionButtons({ id, status: serverStatus, error, confirmText, approveDisabledReason, seenReply, seenTranslation, onDone }: Props) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // the click shows at once; the server answer (or a refusal) follows
  // shown only while the server still reports the status it was clicked from; any newer server status wins
  const [optimistic, setOptimistic] = useState<{ from: ActionStatus; to: ActionStatus } | null>(null);
  const status = optimistic && optimistic.from === serverStatus ? optimistic.to : serverStatus;

  async function act(fn: (id: number) => Promise<unknown>, shown?: ActionStatus) {
    setBusy(true);
    setMsg(null);
    if (shown) setOptimistic({ from: serverStatus, to: shown });
    try {
      await fn(id);
    } catch (e) {
      setOptimistic(null);   // refused: back to what the server says, with the reason
      setMsg(e instanceof ApiError ? e.detail : "Something went wrong.");
    } finally {
      setBusy(false);
      onDone();
    }
  }

  const btn = "rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={status} />
        {status === "pending" && (
          <>
            <button
              type="button"
              disabled={busy || !!approveDisabledReason}
              title={approveDisabledReason}
              onClick={() => (!confirmText || window.confirm(confirmText)) && act((i) => approve(i, seenReply, seenTranslation), "approved")}
              className={`${btn} bg-primary text-on-primary`}
            >
              Approve
            </button>
            <button type="button" disabled={busy} onClick={() => act(reject, "rejected")} className={`${btn} border border-border-strong`}>
              Reject
            </button>
          </>
        )}
        {status === "failed" && (
          <button type="button" disabled={busy} onClick={() => act(retry)} className={`${btn} border border-primary text-primary`}>
            Retry
          </button>
        )}
        {approveDisabledReason && status === "pending" && (
          <span className="text-xs text-text-tertiary">{approveDisabledReason}</span>
        )}
      </div>
      {status === "failed" && error && <p className="text-sm text-state-danger-text">{error}</p>}
      {msg && <p role="alert" className="text-sm text-state-danger-text">{msg}</p>}
    </div>
  );
}
