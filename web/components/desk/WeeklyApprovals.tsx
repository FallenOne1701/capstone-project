"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, weeklyLatest, weeklyRun } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { ActionCard } from "./ActionCard";

const POLL_MS = 5000;
const GIVE_UP_MS = 10 * 60 * 1000;

/** The weekly Google writes wait here: each says exactly what is written where, and runs only on a person's click. */
export function WeeklyApprovals({ onRunDone }: { onRunDone?: () => void }) {
  const { data, error, reload } = usePoll(weeklyLatest, 0);
  const [running, setRunning] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const started = useRef(0);

  useEffect(() => {
    if (running === null) return;
    const id = setInterval(async () => {
      try {
        const attempt = (await weeklyLatest()).latest_attempt;
        if (attempt && attempt.id === running && attempt.status !== "running") {
          setRunning(null);
          await reload();
          onRunDone?.();
          if (attempt.status === "failed") setMsg(`The weekly run failed: ${attempt.error ?? "unknown error"}`);
        }
      } catch {
        /* keep waiting; the server may be busy with the run */
      }
      if (Date.now() - started.current > GIVE_UP_MS) {
        setRunning(null);
        setMsg("The weekly run is taking longer than expected — check back in a few minutes.");
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [running, reload, onRunDone]);

  async function runNow() {
    setMsg(null);
    try {
      const r = await weeklyRun();
      started.current = Date.now();
      setRunning(r.run_id);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : "Couldn't start the weekly run.");
    }
  }

  const missing = error && /no weekly runs/i.test(error);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-headline text-base font-semibold">Waiting for your approval — exactly what gets written</h3>
        <button
          type="button"
          onClick={runNow}
          disabled={running !== null}
          aria-busy={running !== null}
          className="rounded-md border border-primary px-3 py-1.5 text-sm font-medium text-primary disabled:opacity-60"
        >
          {running !== null ? "Running…" : "Run weekly now"}
        </button>
      </div>
      <p className="text-sm text-text-secondary">
        The pulse is rebuilt every Monday. Nothing is written to Google until someone approves the item below.
      </p>
      {msg && <p role="alert" className="text-sm text-state-danger-text">{msg}</p>}
      {missing && <p className="text-sm text-text-secondary">No weekly run yet.</p>}
      {error && !missing && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data?.latest_attempt && data.latest_attempt.id !== data.run.id && data.latest_attempt.status === "failed" && (
        <p className="text-sm text-state-warn-text">
          The newest weekly run failed ({data.latest_attempt.error ?? "unknown error"}); these are still from the last good run.
        </p>
      )}
      {data?.actions.map((a) => <ActionCard key={a.id} a={a} onDone={reload} />)}
      {data && data.actions.length === 0 && (
        <p className="text-sm text-text-secondary">
          The latest run ({data.run.status}) has nothing to approve{data.run.error ? `: ${data.run.error}` : "."}
        </p>
      )}
    </div>
  );
}
