import { EXAMPLE_QUESTIONS } from "@/lib/labels";

const STEPS: [string, string][] = [
  ["Received", "Personal details are hidden before anything is saved."],
  ["Checked", "AI agents find the fact on an official page and check the reply against the rules."],
  ["Waiting for a person", "Someone on our team approves, edits or rejects the reply."],
  ["Answered", "You see the approved answer with its source and the date it was last checked."],
];

/** Fills the Ask tab's right column before any question: what happens to a question, and three to try. */
export function HowItWorks({ onPick }: { onPick: (q: string) => void }) {
  return (
    <section aria-label="How it works" className="rounded-xl border border-border-subtle bg-surface-panel p-6 shadow-sm">
      <h2 className="font-headline text-lg font-semibold">How it works</h2>
      <ol className="mt-4 space-y-3">
        {STEPS.map(([title, line], i) => (
          <li key={title} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-state-pass-bg text-xs font-semibold text-state-pass-text ring-1 ring-state-pass-border">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-semibold">{title}</p>
              <p className="text-sm text-text-secondary">{line}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-text-secondary">
        Answers come only from official pages: each fund&apos;s page on Groww, Groww Help and AMFI. A person approves every answer before you see it.
      </p>
      <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-text-tertiary">Try one</h3>
      <div className="mt-2 flex flex-col gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-lg border border-border-subtle px-3 py-2 text-left text-sm text-text-primary hover:border-primary hover:bg-state-pass-bg"
          >
            {q}
          </button>
        ))}
      </div>
    </section>
  );
}
