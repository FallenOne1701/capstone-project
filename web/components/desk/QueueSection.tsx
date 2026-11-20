"use client";

import { useState } from "react";
import { queueBucket, type QueueFilter } from "@/lib/desk";
import type { QueueItem as Item } from "@/lib/types";
import { QueueItem } from "./QueueItem";

interface Props { data: Item[] | null; error: string | null; reload: () => void }

const FILTERS: { id: QueueFilter; label: string; empty: string }[] = [
  { id: "waiting", label: "Waiting", empty: "Nothing waiting right now." },
  { id: "answered", label: "Answered", empty: "No answered questions yet." },
  { id: "closed", label: "Closed", empty: "No closed questions." },
];

/** Every reply draft waits here for a person: Approve (only once the reviewer passed), Edit, or Reject. */
export function QueueSection({ data, error, reload }: Props) {
  const [filter, setFilter] = useState<QueueFilter>("waiting");
  const shown = data?.filter((i) => queueBucket(i) === filter) ?? null;
  const count = (f: QueueFilter) => data?.filter((i) => queueBucket(i) === f).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-headline text-3xl font-bold tracking-tight">Queue</h1>
          <p className="mt-1 text-text-secondary">
            Nothing is published until someone here approves it. Approve stays off until the reviewer agent passes the draft;
            Edit sends your text back through the reviewer.
          </p>
        </div>
        <div role="radiogroup" aria-label="Show" className="flex flex-wrap gap-2">
          {FILTERS.map((f) => {
            const on = f.id === filter;
            const n = count(f.id);
            return (
              <button
                key={f.id}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setFilter(f.id)}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-medium ${
                  on ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface-panel text-text-secondary hover:border-primary"
                }`}
              >
                {f.label}
                {n !== undefined && <span className={`ml-1.5 ${on ? "opacity-90" : "text-text-tertiary"}`}>{n}</span>}
              </button>
            );
          })}
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data === null && !error && <p className="text-sm text-text-secondary">Loading the queue…</p>}
      {shown !== null && shown.length === 0 && (
        <p className="rounded-xl border border-dashed border-border-strong bg-surface-panel p-8 text-center text-sm text-text-secondary">
          {FILTERS.find((f) => f.id === filter)!.empty}
        </p>
      )}
      <div className="space-y-4">
        {shown?.map((item) => <QueueItem key={item.code} item={item} onChange={reload} />)}
      </div>
    </div>
  );
}
