"use client";

import { useCallback, useState } from "react";
import { ActionCard } from "@/components/console/ActionCard";
import { actions } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const TABS = ["pending", "failed", "executed", "rejected", "all"] as const;

export default function ApprovalsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const fetcher = useCallback(() => actions(tab === "all" ? undefined : tab), [tab]);
  const { data, error, reload } = usePoll(fetcher, 10_000);
  const rows = data ?? [];

  return (
    <div className="space-y-4">
      <h1 className="font-headline text-xl font-semibold">Approvals</h1>
      <div role="tablist" aria-label="Filter actions" className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => {
              setTab(t);
            }}
            className={`rounded-md px-3 py-1.5 text-sm ${tab === t ? "bg-state-pass-bg font-medium text-state-pass-text" : "text-text-secondary"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data && !rows.length && <p className="text-text-secondary">Nothing here.</p>}
      {rows.map((a) => <ActionCard key={a.id} a={a} onDone={reload} />)}
    </div>
  );
}
