"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, weeklyLatest, weeklyRun } from "@/lib/api";

const POLL_MS = 5000;
const GIVE_UP_MS = 10 * 60 * 1000;

/** Starts a weekly run and waits for it to finish; `onRunDone` then reloads the pulse and the approvals. */
export function RunWeeklyButton({ onRunDone }: { onRunDone: () => void }) {
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
          onRunDone();
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
  }, [running, onRunDone]);

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

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <button
        type="button"
        onClick={runNow}
        disabled={running !== null}
        aria-busy={running !== null}
        className="rounded-lg border border-primary bg-surface-panel px-4 py-2 text-sm font-semibold text-primary hover:bg-state-pass-bg disabled:opacity-60"
      >
        {running !== null ? "Running…" : <><span aria-hidden>▶ </span>Run weekly now</>}
      </button>
      {msg && <p role="alert" className="text-sm text-state-danger-text">{msg}</p>}
    </div>
  );
}
