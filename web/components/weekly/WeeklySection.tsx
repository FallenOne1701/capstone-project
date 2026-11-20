"use client";

import { useCallback, useEffect, useState } from "react";
import { ExplainersList } from "@/components/desk/ExplainersList";
import { SourcesList } from "@/components/desk/SourcesList";
import { WeeklyApprovals } from "@/components/desk/WeeklyApprovals";
import { ApiError, weeklySummary } from "@/lib/api";
import { weekHeading } from "@/lib/labels";
import type { WeeklySummary } from "@/lib/types";
import { RunWeeklyButton } from "./RunWeeklyButton";

type State = { kind: "loading" } | { kind: "none" } | { kind: "error" } | { kind: "ok"; data: WeeklySummary };

const CARD = "rounded-xl border border-border-subtle bg-surface-panel p-6 shadow-sm";

/** This week's review pulse, rebuilt automatically every Monday from Play Store reviews. */
export function WeeklySection() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let alive = true;
    weeklySummary()
      .then((data) => alive && setState({ kind: "ok", data }))
      .catch((e) => alive && setState({ kind: e instanceof ApiError && e.status === 404 ? "none" : "error" }));
    return () => {
      alive = false;
    };
  }, [version]); // a finished "Run weekly now" reloads the pulse

  return (
    <section aria-label="Weekly pulse" className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-headline text-3xl font-bold tracking-tight">This week</h1>
          <p className="mt-1 text-text-secondary">
            What Play Store reviews said this week, the questions asked again and again, and the Google writes waiting for a person.
          </p>
        </div>
        <RunWeeklyButton onRunDone={refresh} />
      </div>

      <div className={CARD}>
        {state.kind === "loading" && <p className="text-sm text-text-secondary">Loading this week&apos;s pulse…</p>}
        {state.kind === "none" && <p className="text-sm text-text-secondary">The first weekly pulse hasn&apos;t run yet.</p>}
        {state.kind === "error" && <p className="text-sm text-text-secondary">The weekly pulse can&apos;t be loaded right now.</p>}
        {state.kind === "ok" && <Pulse data={state.data} />}
      </div>

      <WeeklyApprovals version={version} />

      <div className="space-y-4">
        <ExplainersList />
        <SourcesList />
      </div>
    </section>
  );
}

function Pulse({ data }: { data: WeeklySummary }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-headline text-xl font-semibold">{weekHeading(data.week_ending, data.stale)}</h2>
        <p className="text-xs text-text-tertiary">
          From {data.review_count ?? 0} Play Store reviews, {data.window_start} to {data.window_end}. Updated automatically every Monday.
        </p>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">Top themes</h3>
        <ol aria-label="Top themes" className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.themes.map((t, i) => (
            <li key={t.label} className="rounded-lg border border-border-subtle bg-surface-bg p-4">
              <p className="flex items-baseline gap-2">
                <span className="font-mono-token text-xs text-text-tertiary">{i + 1}</span>
                <span className="font-semibold">{t.label}</span>
              </p>
              <p className="mt-1 text-sm text-text-secondary">
                {t.count} reviews · {t.recent_count} in the last 7 days
              </p>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {data.quotes.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">What users said</h3>
            <ul aria-label="What users said" className="mt-2 space-y-2 text-sm">
              {data.quotes.map((q, i) => (
                <li key={i} className="border-l-2 border-primary-container pl-3 italic text-text-secondary">
                  “{q.text}”{q.theme && <span className="not-italic text-xs text-text-tertiary"> — {q.theme}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">Asked repeatedly</h3>
          {data.repeated.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {data.repeated.map((r) => <li key={r.label}>{r.label}: {r.count} questions in 7 days</li>)}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-text-secondary">No question was asked 5 or more times in the last 7 days.</p>
          )}
        </div>
      </div>

      {data.explainer && (
        <div className="rounded-lg border border-state-pass-border bg-state-pass-bg p-4">
          <h3 className="font-semibold">{data.explainer.title}</h3>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
            {data.explainer.bullets.map((b, i) => (
              <li key={i}>
                {b.text}{" "}
                <a href={b.url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">official source</a>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-xs text-text-tertiary">Last checked {data.explainer.last_checked}</p>
        </div>
      )}

      <p className="border-t border-border-subtle pt-3 text-xs text-text-secondary">
        Google Doc: {data.delivery.doc} · Gmail draft: {data.delivery.email_draft}
      </p>
    </div>
  );
}
