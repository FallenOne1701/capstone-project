import type { Metadata } from "next";
import { AskFlow } from "@/components/ask/AskFlow";
import { PublicShell } from "@/components/PublicShell";
import { WeeklySection } from "@/components/weekly/WeeklySection";

export const metadata: Metadata = {
  title: "Groww Support Desk",
  description: "Ask about HDFC mutual funds on Groww. Facts only, checked by AI agents, with the official source.",
};

export default async function Home({ searchParams }: { searchParams: Promise<{ t?: string | string[] }> }) {
  const { t } = await searchParams;
  const code = Array.isArray(t) ? t[0] : t;
  return (
    <PublicShell>
      <h1 className="font-headline text-2xl font-semibold">Ask about HDFC mutual funds</h1>
      <p className="mt-1 text-sm text-text-secondary">
        Fees, exit loads, minimum SIP, how-tos. Facts only, with the official source — our AI agents check every
        answer against official pages and the rules before you see it.
      </p>
      <section aria-label="Ask a question" className="mt-6 rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
        <AskFlow key={code ?? "new"} initialCode={code ?? null} />
      </section>
      <WeeklySection />
    </PublicShell>
  );
}
