"use client";

import { useState } from "react";
import { ActionCard } from "@/components/console/ActionCard";
import { ExplainerCard } from "@/components/console/ExplainerCard";
import { ThemeList } from "@/components/console/ThemeList";
import { ApiError, weeklyLatest, weeklyRun } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function PulsePage() {
  const { data, error, reload } = usePoll(weeklyLatest, 5_000);
  const [msg, setMsg] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const run = data?.run;

  async function runNow() {
    setStarting(true);
    setMsg(null);
    try {
      await weeklyRun();
      await reload();
    } catch (e) {
      setMsg(e instanceof ApiError && e.status === 409 ? "A run is already in progress" : e instanceof ApiError ? e.detail : "Couldn't start the run.");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-headline text-xl font-semibold">Weekly pulse</h1>
        <button
          type="button"
          onClick={runNow}
          disabled={starting || run?.status === "running"}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
        >
          {run?.status === "running" ? "Running…" : "Run now"}
        </button>
      </div>
      {msg && <p role="alert" className="text-sm text-state-warn-text">{msg}</p>}
      {error && !data && <p className="text-text-secondary">{error === "no weekly runs yet" ? "No weekly runs yet — press Run now." : error}</p>}

      {run && (
        <>
          <section aria-label="Run summary" className="rounded-xl border border-border-subtle bg-surface-panel p-4 text-sm">
            <p>
              <strong>Run {run.id}</strong> · {run.status} · {run.window_start} to {run.window_end} ·{" "}
              {run.review_count ?? 0} reviews · {run.llm_calls ?? 0} LLM calls
            </p>
            {run.error && <p className="mt-1 text-state-danger-text">{run.error}</p>}
          </section>

          <section className="space-y-2">
            <h2 className="font-headline font-semibold">Themes</h2>
            <ThemeList themes={data.themes} />
          </section>

          {run.pulse_text && (
            <section aria-labelledby="pulse-text" className="space-y-2">
              <h2 id="pulse-text" className="font-headline font-semibold">Pulse text</h2>
              <pre className="font-mono-token overflow-auto whitespace-pre-wrap rounded-xl border border-border-subtle bg-surface-panel p-4 text-xs leading-relaxed">
                {run.pulse_text}
              </pre>
            </section>
          )}

          <section className="space-y-2">
            <h2 className="font-headline font-semibold">Asked repeatedly</h2>
            {data.repeated.length ? (
              <ul className="list-disc pl-5 text-sm">
                {data.repeated.map((r, i) => (
                  <li key={r.key ?? i}>{r.label}: {r.count} questions ({r.window_start} to {r.window_end})</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-text-secondary">No question reached the threshold in the last 7 days.</p>
            )}
          </section>

          {data.explainer && (
            <section className="space-y-2">
              <h2 className="font-headline font-semibold">Fee explainer</h2>
              <ExplainerCard e={data.explainer} />
            </section>
          )}

          <section className="space-y-2">
            <h2 className="font-headline font-semibold">Actions for this run</h2>
            {data.actions.length ? (
              data.actions.map((a) => <ActionCard key={a.id} a={a} onDone={reload} />)
            ) : (
              <p className="text-sm text-text-secondary">No actions yet.</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
