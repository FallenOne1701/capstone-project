import type { Intent, Preview } from "./types";

export const INTENT_LABELS: Record<Intent, string> = {
  fee_question: "Fee question",
  fund_fact: "Fund fact",
  how_to_process: "How-to",
  advice_request: "Advice request",
  performance_request: "Returns request",
  account_issue: "Account issue",
  out_of_scope: "Out of scope",
};

/** "Fee question · HDFC Mid Cap" — the scheme only when exactly one was understood. */
export function intentLabel(p: Pick<Preview, "intent" | "scheme_names"> & Partial<Preview>): string {
  const intent = INTENT_LABELS[p.intent] ?? p.intent;
  return p.scheme_names.length === 1 ? `${intent} · ${p.scheme_names[0]}` : intent;
}

/** "HDFC Mid Cap or HDFC Small Cap?" */
export function clarifyQuestion(names: string[]): string {
  if (names.length <= 1) return `${names[0] ?? ""}?`;
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}?`;
}

export type StatusWord = "received" | "in review" | "answered" | "failed" | "closed";

export function statusLabel(s: string): StatusWord {
  if (s === "in_review") return "in review";
  if (s === "answered" || s === "failed" || s === "closed") return s;
  return "received";
}

export const CLOSED_TEXT = "We couldn't answer this one.";
export const ASK_AGAIN = "Ask again";

/** What the asker reads while the draft waits: a person approves unless the optional auto mode is on. */
export function waitingText(status: string, approval: "auto" | "person"): string | null {
  if (status !== "in_review") return null;
  return approval === "person"
    ? "Waiting for a person to approve this answer."
    : "Our agents are checking the answer against official sources and the rules…";
}

export const SCOPE_INTENTS: Intent[] = ["advice_request", "performance_request"];
export const SCOPE_NOTICE = "We share facts only and can't advise on buying, selling or returns";
export const STT_FAIL = "Couldn't hear that — try again or type";
export const OUT_OF_SCOPE_NOTICE =
  "We only answer factual questions about HDFC mutual funds on Groww. We can't help with banking, loans, cards, insurance or other products, and we never give advice.";

/** Shown at once on the confirm card and ticket: advice/returns → facts-only notice; off-topic → what we answer. */
export function scopeNotice(intent: string | null | undefined): string | null {
  if (intent === "advice_request" || intent === "performance_request") return SCOPE_NOTICE;
  if (intent === "out_of_scope") return OUT_OF_SCOPE_NOTICE;
  return null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "This week · week ending 17 Nov 2026"; an older pulse is never called this week. */
export function weekHeading(weekEnding: string, stale: boolean): string {
  const [y, m, d] = weekEnding.split("-").map(Number);
  const when = `${d} ${MONTHS[m - 1]} ${y}`;
  return `${stale ? "Latest pulse" : "This week"} · week ending ${when}`;
}

/** The approval title states exactly what is written where; the Gmail one also says it is never sent. */
export function actionTitle(a: { type: string; target_label: string }): string {
  return a.type === "email_draft" ? `${a.target_label}, not sent` : a.target_label;
}

/** How long the asker's page waits before asking again; null = stop. A failed ticket can still be re-run by a
 * person in the queue, so it is watched slowly instead of given up on. */
export function nextPollMs(status: string): number | null {
  if (status === "answered" || status === "closed") return null;
  if (status === "received") return 1000;   // the desk is working: the draft is seconds away
  return status === "failed" ? 15000 : 3000;
}

export type StepState = "done" | "current" | "todo";

/** The ticket's 4 steps; none for a closed or failed ticket. */
export function progressSteps(status: string, approval: "auto" | "person"): { label: string; state: StepState }[] | null {
  if (status === "closed" || status === "failed") return null;
  const labels = ["Received", "Checked", approval === "auto" ? "Approving" : "Waiting for a person", "Answered"];
  const at = status === "answered" ? 4 : status === "in_review" ? 2 : 1;   // received: in, now being checked
  return labels.map((label, i) => ({ label, state: i < at ? "done" : i === at ? "current" : "todo" }));
}

/** Clicking one fills the question box; the person still presses Continue. */
export const EXAMPLE_QUESTIONS: readonly string[] = [
  "What is the expense ratio of HDFC Mid Cap Fund?",
  "What is the minimum SIP amount for HDFC Small Cap Fund?",
  "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
];
