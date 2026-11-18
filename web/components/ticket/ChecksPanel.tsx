import type { Checks } from "@/lib/types";

const AGENT: Record<string, string> = {
  facts: "Facts agent — looked up the official fund page",
  pattern: "Pattern agent — compared with what reviewers report",
  compliance: "Compliance agent — screened for advice, returns and personal data",
  reviewer: "Reviewer agent — approved the final reply",
};
const CHECK: Record<string, string> = {
  citation: "source link matches the fact",
  advice: "no investment advice",
  performance: "no return figures",
  pii: "no personal details",
  shape: "checked date included",
};

/** What the agents did before this answer was published — shown so anyone can see why it can be trusted. */
export function ChecksPanel({ checks }: { checks: Checks }) {
  return (
    <details className="mt-3 rounded-md border border-border-subtle bg-surface-panel p-3 text-sm">
      <summary className="cursor-pointer font-medium text-primary">How this was checked</summary>
      <div className="mt-2 space-y-2 text-text-secondary">
        {checks.fallback && <p className="text-state-warn-text">{checks.fallback}</p>}
        <ul className="list-disc space-y-0.5 pl-5">
          {checks.agents.map((a) => <li key={a}>{AGENT[a] ?? a}</li>)}
        </ul>
        <p>
          <span className="font-medium text-text-primary">Review: {checks.review === "pass" ? "passed" : checks.review}</span>
          {" — "}
          {checks.checks.map((c) => CHECK[c] ?? c).join(" · ")}
        </p>
        {checks.citation && (
          <p>
            Source:{" "}
            <a href={checks.citation} target="_blank" rel="noreferrer" className="break-all text-primary underline">
              {checks.citation}
            </a>
            {checks.last_checked && <> · last checked {checks.last_checked}</>}
          </p>
        )}
        {checks.reused_explainer && <p>Reused fee explainer #{checks.reused_explainer} from the weekly pulse.</p>}
      </div>
    </details>
  );
}
