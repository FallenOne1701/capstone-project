"use client";

import { useRef } from "react";
import type { Tab } from "@/lib/desk";

export const TABS: { id: Tab; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "week", label: "This week" },
  { id: "queue", label: "Queue" },
];

interface Props {
  tab: Tab;
  onTab: (t: Tab) => void;
  /** tickets waiting for a person; null when the queue could not load (no badge then) */
  waiting: number | null;
  /** a weekly Google write waits for a person or failed */
  weekDot: boolean;
}

/** "Support Desk" bar with the tab row: Ask | This week | Queue. Arrow keys, Home and End move between tabs. */
export function DeskHeader({ tab, onTab, waiting, weekDot }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: React.KeyboardEvent, i: number) {
    const last = TABS.length - 1;
    const to = { ArrowRight: i === last ? 0 : i + 1, ArrowLeft: i === 0 ? last : i - 1, Home: 0, End: last }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    onTab(TABS[to].id);
    refs.current[to]?.focus();
  }

  return (
    <header className="border-b border-border-subtle bg-surface-panel">
      <div className="mx-auto max-w-7xl px-4 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 pb-2">
          <div className="flex items-center gap-3">
            <span className="font-headline text-lg font-bold tracking-tight">Support Desk</span>
            <span className="rounded-md bg-surface-bg px-2 py-0.5 text-xs font-medium text-text-secondary ring-1 ring-border-subtle">
              HDFC Mutual Funds
            </span>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full border border-state-pass-border bg-state-pass-bg px-3 py-1 text-xs font-medium text-state-pass-text">
            <span className="h-2 w-2 rounded-full bg-primary" aria-hidden />
            A person approves every answer
          </span>
        </div>
        <div role="tablist" aria-label="Desk" className="-mb-px flex gap-6 overflow-x-auto">
          {TABS.map((t, i) => {
            const selected = t.id === tab;
            const badge = t.id === "queue" && waiting !== null && waiting > 0 ? waiting : null;
            return (
              <button
                key={t.id}
                ref={(el) => { refs.current[i] = el; }}
                type="button"
                role="tab"
                id={`tab-${t.id}`}
                aria-controls={`panel-${t.id}`}
                aria-selected={selected}
                aria-label={badge !== null ? `Queue, ${badge} waiting` : t.id === "week" && weekDot ? "This week, needs you" : undefined}
                tabIndex={selected ? 0 : -1}
                onClick={() => onTab(t.id)}
                onKeyDown={(e) => onKey(e, i)}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                  selected ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text-primary"
                }`}
              >
                {t.label}
                {badge !== null && (
                  <span className="rounded-full bg-state-warn-bg px-1.5 text-xs font-semibold text-state-warn-text ring-1 ring-state-warn-border">
                    {badge}
                  </span>
                )}
                {t.id === "week" && weekDot && <span className="h-2 w-2 rounded-full bg-primary" aria-hidden />}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
}
