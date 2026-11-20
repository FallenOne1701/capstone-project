import type { Action, QueueItem, WeeklyLatest } from "./types";

export type Tab = "ask" | "week" | "queue";

/** `?tab=` → the tab to open; anything unknown opens Ask. */
export function parseTab(v: string | string[] | null | undefined): Tab {
  const s = Array.isArray(v) ? v[0] : v;
  return s === "week" || s === "queue" ? s : "ask";
}

/** The page address for a tab and an open ticket: "/", "/?t=CODE", "/?tab=queue", "/?t=CODE&tab=week". */
export function deskHref(tab: Tab, code: string | null): string {
  const parts: string[] = [];
  if (code) parts.push(`t=${encodeURIComponent(code)}`);
  if (tab !== "ask") parts.push(`tab=${tab}`);
  return parts.length ? `/?${parts.join("&")}` : "/";
}

export type QueueFilter = "waiting" | "answered" | "closed";

/** Answered and closed are done; everything else still needs someone, so no ticket falls out of every filter. */
export function queueBucket(item: Pick<QueueItem, "status">): QueueFilter {
  return item.status === "answered" || item.status === "closed" ? item.status : "waiting";
}

/** The Queue badge number; null (no badge) when the queue could not load. */
export function waitingCount(items: Pick<QueueItem, "status">[] | null): number | null {
  return items === null ? null : items.filter((i) => queueBucket(i) === "waiting").length;
}

const WEEKLY_TYPES: Action["type"][] = ["doc_append", "email_draft"];

/** This week gets a dot when a Google write waits for a person or failed. */
export function weeklyNeedsYou(latest: Pick<WeeklyLatest, "actions"> | null): boolean {
  return !!latest?.actions.some((a) => WEEKLY_TYPES.includes(a.type) && (a.status === "pending" || a.status === "failed"));
}
