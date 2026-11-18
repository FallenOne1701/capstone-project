"use client";

import { ExplainerCard } from "@/components/console/ExplainerCard";
import { explainers } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function ExplainersPage() {
  const { data, error } = usePoll(explainers, 0);
  return (
    <div className="space-y-4">
      <h1 className="font-headline text-xl font-semibold">Explainers</h1>
      <p className="text-sm text-text-secondary">
        Fee explainers built each week from official pages. The canonical one is reused to answer matching questions.
      </p>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      {data?.length === 0 && <p className="text-text-secondary">No explainers yet — they come from the weekly run.</p>}
      {data?.map((e) => <ExplainerCard key={e.id} e={e} />)}
    </div>
  );
}
