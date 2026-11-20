"use client";

import { useEffect, useRef } from "react";
import { weeklyLatest } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";
import { ActionCard } from "./ActionCard";

/** The weekly Google writes wait here: each says exactly what is written where, and runs only on a person's click. */
export function WeeklyApprovals({ version }: { version: number }) {
  const { data, error, reload } = usePoll(weeklyLatest, 0);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void reload(); // a finished "Run weekly now" brings new items
  }, [version, reload]);

  const missing = error && /no weekly runs/i.test(error);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-headline text-lg font-semibold">Waiting for your approval</h2>
        <p className="text-sm text-text-secondary">
          Exactly what gets written, and where. Nothing is written to Google until someone approves that item.
        </p>
      </div>
      {missing && <p className="text-sm text-text-secondary">No weekly run yet.</p>}
      {error && !missing && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data?.latest_attempt && data.latest_attempt.id !== data.run.id && data.latest_attempt.status === "failed" && (
        <p className="text-sm text-state-warn-text">
          The newest weekly run failed ({data.latest_attempt.error ?? "unknown error"}); these are still from the last good run.
        </p>
      )}
      {data && data.actions.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.actions.map((a) => <ActionCard key={a.id} a={a} onDone={reload} />)}
        </div>
      )}
      {data && data.actions.length === 0 && (
        <p className="text-sm text-text-secondary">
          The latest run ({data.run.status}) has nothing to approve{data.run.error ? `: ${data.run.error}` : "."}
        </p>
      )}
    </div>
  );
}
