"use client";

import { explainers } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { ExplainerCard } from "./ExplainerCard";

const ORDER: Record<string, number> = { canonical: 0, draft: 1, superseded: 2, rejected: 3 };

/** Fee explainers: an approved Doc append makes one canonical, and later answers reuse it. */
export function ExplainersList() {
  const { data, error } = usePoll(explainers, 0);
  const sorted = data ? [...data].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || b.id - a.id) : null;
  return (
    <details open className="rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
      <summary className="cursor-pointer font-headline text-base font-semibold">
        Fee explainers{data ? ` — ${data.filter((e) => e.status === "canonical").length} canonical, in use` : ""}
      </summary>
      {error && <p role="alert" className="mt-2 text-sm text-state-danger-text">{error}</p>}
      {sorted && sorted.length === 0 && <p className="mt-2 text-sm text-text-secondary">No explainers yet.</p>}
      <div className="mt-3 space-y-3">{sorted?.map((e) => <ExplainerCard key={e.id} e={e} />)}</div>
    </details>
  );
}
