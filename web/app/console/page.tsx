"use client";

import { QueueItem } from "@/components/console/QueueItem";
import { queue } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function QueuePage() {
  const { data, error, reload } = usePoll(queue, 10_000);
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="font-headline text-xl font-semibold">Queue</h1>
        <span className="text-xs text-text-tertiary">Newest first · refreshes every 10 s</span>
      </div>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data === null && !error && <p className="text-text-secondary">Loading…</p>}
      {data?.length === 0 && <p className="text-text-secondary">No questions yet.</p>}
      {data?.map((item) => <QueueItem key={`${item.code}-${item.draft?.id ?? 0}`} item={item} onChange={reload} />)}
    </div>
  );
}
