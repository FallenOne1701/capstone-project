"use client";

import type { Action } from "@/lib/types";
import { ActionButtons } from "./ActionButtons";

const CONFIRM: Record<string, string> = {
  doc_append: "This writes to Google Docs. Approve?",
  email_draft: "This creates a Gmail draft (not sent). Approve?",
};
const TYPE: Record<string, string> = {
  doc_append: "Google Doc append",
  email_draft: "Gmail draft",
  reply_publish: "Publish reply",
};

const when = (s: string | null) => (s ? new Date(s).toLocaleString() : "—");

export function ActionCard({ a, onDone }: { a: Action; onDone: () => void }) {
  return (
    <article aria-label={`Action ${a.id}`} className="rounded-xl border border-border-subtle bg-surface-panel p-4 shadow-sm">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono-token text-sm text-text-tertiary">#{a.id}</span>
        <span className="font-medium">{TYPE[a.type] ?? a.type}</span>
        <span className="text-sm text-text-secondary">{a.target_label}</span>
      </header>
      <p className="mt-1 text-xs text-text-tertiary">
        created {when(a.created_at)} · decided {when(a.decided_at)}
        {a.executed_at && <> · executed {when(a.executed_at)}</>}
        {a.source_ref && <> · from {a.source_ref}</>}
      </p>
      {a.content && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-primary">Content preview</summary>
          <pre className="font-mono-token mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-surface-bg p-3 text-xs">{a.content}</pre>
        </details>
      )}
      <div className="mt-3">
        <ActionButtons id={a.id} status={a.status} error={a.error} confirmText={CONFIRM[a.type]} onDone={onDone} />
      </div>
    </article>
  );
}
