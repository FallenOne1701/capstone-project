import type { Explainer } from "@/lib/types";

const STATUS: Record<string, string> = {
  canonical: "border-state-pass-border bg-state-pass-bg text-state-pass-text",
  draft: "border-state-warn-border bg-state-warn-bg text-state-warn-text",
  superseded: "border-border-strong bg-surface-bg text-text-secondary",
  rejected: "border-state-danger-border bg-state-danger-bg text-state-danger-text",
};

export function ExplainerCard({ e }: { e: Explainer }) {
  return (
    <article aria-label={`Explainer ${e.id}`} className="rounded-xl border border-border-subtle bg-surface-panel p-4 shadow-sm">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono-token text-sm text-text-tertiary">#{e.id}</span>
        <span className="font-medium">{e.title}</span>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS[e.status] ?? STATUS.superseded}`}>{e.status}</span>
      </header>
      <p className="mt-1 text-xs text-text-tertiary">
        topic {e.topic}{e.run_id != null && <> · weekly run {e.run_id}</>} · last checked {e.last_checked}
        {e.canonical_at && <> · canonical since {new Date(e.canonical_at).toLocaleDateString()}</>}
        {" "}· reused in {e.reuse_count} {e.reuse_count === 1 ? "reply" : "replies"}
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
        {e.bullets.map((b, i) => (
          <li key={i}>
            {b.text}{" "}
            <a href={b.url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">source</a>
          </li>
        ))}
      </ol>
    </article>
  );
}
