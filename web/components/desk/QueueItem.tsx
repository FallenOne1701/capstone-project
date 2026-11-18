"use client";

import { useState } from "react";
import { Redacted } from "@/components/Redacted";
import { ApiError, editDraft, reprocess } from "@/lib/api";
import { INTENT_LABELS, statusLabel } from "@/lib/labels";
import type { QueueItem as Item } from "@/lib/types";
import { ActionButtons, StatusBadge } from "./ActionButtons";

const LANG: Record<string, string> = { en: "English", hi: "Hindi", hinglish: "Hinglish" };

export function QueueItem({ item, onChange }: { item: Item; onChange: () => void }) {
  const d = item.draft;
  const a = item.action;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(d?.reply ?? "");
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!d) return;
    setBusy(true);
    setErr(null);
    try {
      const hadHindi = !!d.translation;
      await editDraft(d.id, text);
      setEditing(false);
      setNote(hadHindi ? "Hindi translation removed — the edited English will be published." : null);
      onChange();
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : "Couldn't save the edit.");
    } finally {
      setBusy(false);
    }
  }

  async function rerun() {
    setBusy(true);
    setErr(null);
    try {
      await reprocess(item.code);
      onChange();
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : "Couldn't re-run the desk.");
    } finally {
      setBusy(false);
    }
  }

  const blocked = d && d.review_status !== "pass";
  return (
    <article aria-label={item.code} className="rounded-xl border border-border-subtle bg-surface-panel p-4 shadow-sm">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono-token font-semibold">{item.code}</span>
        <StatusBadge status={statusLabel(item.status)} />
        {item.intent && <span className="text-text-secondary">{INTENT_LABELS[item.intent] ?? item.intent}</span>}
        <span className="text-text-tertiary">· {LANG[item.language] ?? item.language}</span>
        <span className="ml-auto text-xs text-text-tertiary">{new Date(item.created_at).toLocaleString()}</span>
      </header>

      <p className="mt-3 text-text-primary"><Redacted text={item.question} /></p>
      {item.pii_types.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1" aria-label="Personal details hidden">
          {item.pii_types.map((p) => (
            <span key={p} className="font-mono-token rounded bg-redaction-bg px-1.5 py-0.5 text-xs text-redaction-text">{p}</span>
          ))}
        </div>
      )}

      {d ? (
        <div className="mt-4 space-y-3 border-t border-border-subtle pt-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full border px-2 py-0.5 font-medium ${blocked ? "border-state-danger-border bg-state-danger-bg text-state-danger-text" : "border-state-pass-border bg-state-pass-bg text-state-pass-text"}`}>
              review: {d.review_status}
            </span>
            {d.edited && <span className="rounded-full border border-border-strong px-2 py-0.5">edited</span>}
            {d.reused_explainer_id && (
              <span className="rounded-full border border-primary px-2 py-0.5 text-primary">Reused explainer #{d.reused_explainer_id}</span>
            )}
            <span className="text-text-tertiary">{d.disposition}</span>
          </div>

          {editing ? (
            <div className="space-y-2">
              <label htmlFor={`edit-${d.id}`} className="sr-only">Edit reply</label>
              <textarea
                id={`edit-${d.id}`}
                aria-label="Edit reply"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                className="w-full rounded-md border border-border-strong p-2 text-sm"
              />
              <div className="flex gap-2">
                <button type="button" disabled={busy} onClick={save} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50">
                  Save edit
                </button>
                <button type="button" onClick={() => { setEditing(false); setText(d.reply); }} className="rounded-md border border-border-strong px-3 py-1.5 text-sm">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="whitespace-pre-line text-sm leading-relaxed">{d.reply}</p>
          )}

          {d.translation && !editing && (
            <div className="rounded-md border border-border-subtle bg-surface-bg p-3">
              <p className="text-xs font-medium text-text-tertiary">Published in Hindi</p>
              <p lang="hi" className="mt-1 whitespace-pre-line text-sm">{d.translation.text}</p>
            </div>
          )}
          {note && <p className="text-sm text-state-warn-text">{note}</p>}

          <dl className="grid gap-x-4 gap-y-1 text-xs text-text-secondary sm:grid-cols-[auto_1fr]">
            {d.citation && (
              <>
                <dt className="font-medium">Source</dt>
                <dd><a href={d.citation} target="_blank" rel="noreferrer" className="break-all text-primary underline">{d.citation}</a></dd>
              </>
            )}
            {d.last_checked && (<><dt className="font-medium">Last checked</dt><dd>{d.last_checked}</dd></>)}
            <dt className="font-medium">Routing</dt>
            <dd>{d.routing.team} · {d.routing.priority} · {d.routing.why}</dd>
          </dl>

          {d.review_failures.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-state-danger-text">
              {d.review_failures.map((f, i) => <li key={i}><strong>{f.check}</strong>: {f.detail}</li>)}
            </ul>
          )}

          {a && (
            <div className="flex flex-wrap items-start gap-2">
              <ActionButtons
                id={a.id}
                status={a.status}
                error={a.error}
                approveDisabledReason={blocked ? "Edit it first — the reviewer blocked this draft" : undefined}
                seenReply={d.reply}
                onDone={onChange}
              />
              {a.status === "pending" && !editing && (
                <button type="button" onClick={() => { setText(d.reply); setEditing(true); }} className="rounded-md border border-border-strong px-3 py-1.5 text-sm">
                  Edit
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        (item.status === "failed" || item.status === "received") && (
          <div className="mt-4 flex items-center gap-3 border-t border-border-subtle pt-3 text-sm">
            <span className="text-text-secondary">
              {item.status === "failed" ? "The desk failed on this ticket." : "Waiting for the desk…"}
            </span>
            <button type="button" disabled={busy} onClick={rerun} className="rounded-md border border-primary px-3 py-1.5 text-primary disabled:opacity-50">
              Re-run desk
            </button>
          </div>
        )
      )}
      {err && <p role="alert" className="mt-2 text-sm text-state-danger-text">{err}</p>}
    </article>
  );
}
