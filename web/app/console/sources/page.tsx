"use client";

import { useState } from "react";
import { ApiError, refreshSources, sources } from "@/lib/api";
import type { RefreshResult } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const BADGE: Record<string, string> = {
  ok: "border-state-pass-border bg-state-pass-bg text-state-pass-text",
  stale: "border-state-warn-border bg-state-warn-bg text-state-warn-text",
  error: "border-state-danger-border bg-state-danger-bg text-state-danger-text",
};

export default function SourcesPage() {
  const { data, error, reload } = usePoll(sources, 0);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RefreshResult | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    setBusy(true);
    setMsg(null);
    setResult(null);
    try {
      setResult(await refreshSources());
      await reload();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-headline text-xl font-semibold">Sources</h1>
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          aria-busy={busy}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-60"
        >
          {busy && <span aria-hidden className="h-3 w-3 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />}
          {busy ? "Refreshing… (about a minute)" : "Refresh now"}
        </button>
      </div>
      {result && (
        <p role="status" className="text-sm text-text-secondary">
          {result.ok} ok · {result.stale} stale · {result.error} error · {result.reindexed ? "index rebuilt" : "index unchanged"}
        </p>
      )}
      {(msg || error) && <p role="alert" className="text-sm text-state-danger-text">{msg || error}</p>}
      {data && (
        <div className="overflow-x-auto rounded-xl border border-border-subtle bg-surface-panel">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border-subtle text-xs uppercase text-text-tertiary">
              <tr>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Last checked</th>
                <th className="px-3 py-2">Error</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.url} className="border-b border-border-subtle last:border-0">
                  <td className="px-3 py-2">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-primary underline">{s.title}</a>
                  </td>
                  <td className="px-3 py-2 text-text-secondary">{s.kind}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[s.status] ?? "border-border-strong text-text-secondary"}`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-text-secondary">{s.last_checked ?? "—"}</td>
                  <td className="px-3 py-2 text-xs text-state-danger-text">{s.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
