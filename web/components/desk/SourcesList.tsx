"use client";

import { sources } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const BADGE: Record<string, string> = {
  ok: "border-state-pass-border bg-state-pass-bg text-state-pass-text",
  stale: "border-state-warn-border bg-state-warn-bg text-state-warn-text",
  error: "border-state-danger-border bg-state-danger-bg text-state-danger-text",
};

/** The official pages every answer is checked against, with when each was last checked. */
export function SourcesList() {
  const { data, error } = usePoll(sources, 0);
  return (
    <details open className="rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
      <summary className="cursor-pointer font-headline text-base font-semibold">
        Sources{data ? ` (${data.length})` : ""}
      </summary>
      {error && <p role="alert" className="mt-2 text-sm text-state-danger-text">{error}</p>}
      {data && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border-subtle text-xs uppercase text-text-tertiary">
              <tr>
                <th className="px-2 py-1.5">Title</th>
                <th className="px-2 py-1.5">Kind</th>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5">Last checked</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.url} className="border-b border-border-subtle last:border-0">
                  <td className="px-2 py-1.5">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-primary underline">{s.title}</a>
                  </td>
                  <td className="px-2 py-1.5 text-text-secondary">{s.kind}</td>
                  <td className="px-2 py-1.5">
                    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[s.status] ?? "border-border-strong text-text-secondary"}`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-text-secondary">{s.last_checked ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}
