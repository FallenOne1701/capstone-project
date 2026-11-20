"use client";

import type { Action } from "@/lib/types";
import { actionTitle } from "@/lib/labels";
import { ActionButtons } from "./ActionButtons";

const CONFIRM: Record<string, string> = {
  doc_append: "This writes to Google Docs. Approve?",
  email_draft: "This creates a Gmail draft (not sent). Approve?",
};
const TYPE: Record<string, string> = {
  doc_append: "Google Docs",
  email_draft: "Gmail draft",
  reply_publish: "Publish reply",
};

const when = (s: string | null) => (s ? new Date(s).toLocaleString() : "—");

export function ActionCard({ a, onDone }: { a: Action; onDone: () => void }) {
  const textId = `action-${a.id}-text`;
  return (
    <article aria-label={`Action ${a.id}`} className="flex min-w-0 flex-col rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">Where it goes</span>
        <span className="rounded-md bg-state-pass-bg px-2 py-0.5 text-xs font-medium text-state-pass-text ring-1 ring-state-pass-border">
          {TYPE[a.type] ?? a.type}
        </span>
        <span className="ml-auto font-mono-token text-xs text-text-tertiary">#{a.id}</span>
      </header>
      <h3 className="mt-2 font-semibold text-text-primary">{actionTitle(a)}</h3>
      <p className="mt-1 text-xs text-text-tertiary">
        created {when(a.created_at)} · decided {when(a.decided_at)}
        {a.executed_at && <> · executed {when(a.executed_at)}</>}
        {a.source_ref && <> · from {a.source_ref}</>}
      </p>
      {a.content && (
        <div className="mt-3">
          <p id={textId} className="text-xs font-medium text-text-secondary">Exactly what will be written</p>
          <pre
            aria-labelledby={textId}
            tabIndex={0}
            className="font-mono-token mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border-subtle bg-surface-bg p-3 text-xs"
          >
            {a.content}
          </pre>
        </div>
      )}
      <div className="mt-auto pt-4">
        <ActionButtons id={a.id} status={a.status} error={a.error} confirmText={CONFIRM[a.type]} onDone={onDone} />
      </div>
    </article>
  );
}
