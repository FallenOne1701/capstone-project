"use client";

import type { QueueItem as Item } from "@/lib/types";
import { QueueItem } from "./QueueItem";

interface Props { data: Item[] | null; error: string | null; reload: () => void }

/** Every reply draft waits here for a person: Approve (only once the reviewer passed), Edit, or Reject. */
export function QueueSection({ data, error, reload }: Props) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-headline text-lg font-semibold">Queue — drafts waiting for a person</h2>
        <p className="text-sm text-text-secondary">
          Nothing is published until someone here approves it. Approve stays off until the reviewer agent passes the draft;
          Edit sends your text back through the reviewer.
        </p>
      </div>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data === null && !error && <p className="text-sm text-text-secondary">Loading the queue…</p>}
      {data !== null && data.length === 0 && <p className="text-sm text-text-secondary">Nothing waiting right now.</p>}
      {data?.map((item) => <QueueItem key={item.code} item={item} onChange={reload} />)}
    </div>
  );
}
