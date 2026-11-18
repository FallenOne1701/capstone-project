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

export type StatusWord = "received" | "in review" | "answered" | "failed";

export function statusLabel(s: string): StatusWord {
  if (s === "in_review") return "in review";
  if (s === "answered" || s === "failed") return s;
  return "received";
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
