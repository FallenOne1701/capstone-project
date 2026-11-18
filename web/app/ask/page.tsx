import type { Metadata } from "next";
import { AskFlow } from "@/components/ask/AskFlow";
import { PublicShell } from "@/components/PublicShell";

export const metadata: Metadata = { title: "Ask a question · Groww Support Desk" };

export default function AskPage() {
  return (
    <PublicShell>
      <h1 className="font-headline text-2xl font-semibold">Ask about HDFC mutual funds</h1>
      <p className="mt-1 text-sm text-text-secondary">
        Fees, exit loads, minimum SIP, how-tos. We share facts only, with the official source — a person checks
        every answer before you see it.
      </p>
      <div className="mt-6 rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
        <AskFlow />
      </div>
    </PublicShell>
  );
}
