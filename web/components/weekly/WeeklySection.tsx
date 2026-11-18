"use client";

import { useEffect, useState } from "react";
import { ApiError, weeklySummary } from "@/lib/api";
import { weekHeading } from "@/lib/labels";
import type { WeeklySummary } from "@/lib/types";

type State = { kind: "loading" } | { kind: "none" } | { kind: "error" } | { kind: "ok"; data: WeeklySummary };

/** This week's review pulse, rebuilt automatically every Monday from Play Store reviews. */
export function WeeklySection() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    weeklySummary()
      .then((data) => alive && setState({ kind: "ok", data }))
      .catch((e) => alive && setState({ kind: e instanceof ApiError && e.status === 404 ? "none" : "error" }));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section aria-label="Weekly pulse" className="mt-8 rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
      {state.kind === "loading" && <p className="text-sm text-text-secondary">Loading this week&apos;s pulse…</p>}
      {state.kind === "none" && <p className="text-sm text-text-secondary">The first weekly pulse hasn&apos;t run yet.</p>}
      {state.kind === "error" && <p className="text-sm text-text-secondary">The weekly pulse can&apos;t be loaded right now.</p>}
      {state.kind === "ok" && <Pulse data={state.data} />}
    </section>
  );
}

function Pulse({ data }: { data: WeeklySummary }) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-headline text-lg font-semibold">{weekHeading(data.week_ending, data.stale)}</h2>
        <p className="text-xs text-text-tertiary">
          From {data.review_count ?? 0} Play Store reviews, {data.window_start} to {data.window_end}. Updated automatically every Monday.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold">Top themes</h3>
        <ol aria-label="Top themes" className="mt-1 space-y-1 text-sm">
          {data.themes.map((t, i) => (
            <li key={t.label} className="flex flex-wrap gap-x-2">
              <span className="font-mono-token text-text-tertiary">{i + 1}.</span>
              <span className="font-medium">{t.label}</span>
              <span className="text-text-secondary">{t.count} reviews · {t.recent_count} in the last 7 days</span>
            </li>
          ))}
        </ol>
      </div>

      {data.quotes.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">What users said</h3>
          <ul aria-label="What users said" className="mt-1 space-y-1.5 text-sm">
            {data.quotes.map((q, i) => (
              <li key={i} className="border-l-2 border-border-strong pl-3 italic text-text-secondary">
                “{q.text}”{q.theme && <span className="not-italic text-xs text-text-tertiary"> — {q.theme}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold">Asked repeatedly</h3>
        {data.repeated.length ? (
          <ul className="mt-1 list-disc pl-5 text-sm">
            {data.repeated.map((r) => <li key={r.label}>{r.label}: {r.count} questions in 7 days</li>)}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-text-secondary">No question was asked 5 or more times in the last 7 days.</p>
        )}
      </div>

      {data.explainer && (
        <div>
          <h3 className="text-sm font-semibold">{data.explainer.title}</h3>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">
            {data.explainer.bullets.map((b, i) => (
              <li key={i}>
                {b.text}{" "}
                <a href={b.url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">official source</a>
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-text-tertiary">Last checked {data.explainer.last_checked}</p>
        </div>
      )}

      <p className="border-t border-border-subtle pt-3 text-xs text-text-secondary">
        Google Doc: {data.delivery.doc} · Gmail draft: {data.delivery.email_draft}
      </p>
    </div>
  );
}
