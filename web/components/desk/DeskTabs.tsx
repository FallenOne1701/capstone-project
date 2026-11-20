"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AskFlow } from "@/components/ask/AskFlow";
import { DeskHeader } from "@/components/DeskHeader";
import { QueueSection } from "@/components/desk/QueueSection";
import { WeeklySection } from "@/components/weekly/WeeklySection";
import { deskQueue, weeklyLatest } from "@/lib/api";
import { deskHref, type Tab, waitingCount, weeklyNeedsYou } from "@/lib/desk";
import { usePoll } from "@/lib/usePoll";

const QUEUE_POLL_MS = 5000;
const WEEK_POLL_MS = 30000;

function Panel({ id, tab, children }: { id: Tab; tab: Tab; children: React.ReactNode }) {
  return (
    <section role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} hidden={tab !== id}>
      {children}
    </section>
  );
}

/** The desk: all three tabs stay mounted (nothing typed or opened is lost); the address keeps the tab and ticket. */
export function DeskTabs({ initialTab, initialCode }: { initialTab: Tab; initialCode: string | null }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [code, setCode] = useState<string | null>(initialCode);
  const queue = usePoll(deskQueue, QUEUE_POLL_MS);
  const week = usePoll(weeklyLatest, WEEK_POLL_MS);

  useEffect(() => {
    const href = deskHref(tab, code);
    if (`${window.location.pathname}${window.location.search}` !== href) router.replace(href, { scroll: false });
  }, [tab, code, router]);

  return (
    <>
      <DeskHeader tab={tab} onTab={setTab} waiting={waitingCount(queue.data)} weekDot={weeklyNeedsYou(week.data)} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-8">
        <Panel id="ask" tab={tab}>
          <h1 className="font-headline text-3xl font-bold tracking-tight">Ask about HDFC mutual funds</h1>
          <p className="mt-1 text-text-secondary">
            Fees, exit loads, minimum SIP, how-tos. Facts only, with the official source — our AI agents check every
            answer against official pages and the rules, and a person approves it before you see it.
          </p>
          <div className="mt-6">
            <AskFlow initialCode={initialCode} onCode={setCode} />
          </div>
        </Panel>
        <Panel id="week" tab={tab}>
          <WeeklySection />
        </Panel>
        <Panel id="queue" tab={tab}>
          <QueueSection data={queue.data} error={queue.error} reload={queue.reload} />
        </Panel>
      </main>
    </>
  );
}
