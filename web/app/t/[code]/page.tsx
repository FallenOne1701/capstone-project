import type { Metadata } from "next";
import { PublicShell } from "@/components/PublicShell";
import { TicketStatus } from "@/components/ticket/TicketStatus";

export const metadata: Metadata = { title: "Your ticket · Groww Support Desk" };

export default async function TicketPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return (
    <PublicShell>
      <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Ticket</p>
      <h1 className="font-headline font-mono-token text-2xl font-semibold">{code}</h1>
      <p className="mt-1 text-sm text-text-secondary">Keep this page open or bookmark it — the answer appears here once it&apos;s approved.</p>
      <div className="mt-6 rounded-xl border border-border-subtle bg-surface-panel p-5 shadow-sm">
        <TicketStatus code={code} />
      </div>
    </PublicShell>
  );
}
