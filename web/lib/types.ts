// Mirrors the API's JSON. Keep in step with api/app/api/{public,console}.py.

export type Intent =
  | "fee_question" | "fund_fact" | "how_to_process" | "advice_request"
  | "performance_request" | "account_issue" | "out_of_scope";
export type Language = "en" | "hi" | "hinglish";
export type TicketStatus = "received" | "in_review" | "answered" | "failed";

export interface Preview {
  redacted_text: string;
  pii_types: string[];
  intent: Intent;
  scheme_ids: string[];
  language: Language;
  needs_clarification: boolean;
  options: string[];
  scheme_names: string[];
}

export interface AskResult { code: string; status: TicketStatus; notice: string | null }

export interface LocalText { language: "hi"; text: string }

export interface TicketView {
  code: string;
  status: TicketStatus;
  question: string;
  answer: string | null;
  answer_local: LocalText | null;
  answered_at: string | null;
  language: Language;
  intent: Intent | null;
  checks: Checks | null;
}

export interface Checks {
  agents: string[];
  review: string;
  checks: string[];
  citation: string | null;
  last_checked: string | null;
  reused_explainer: number | null;
  fallback: string | null;
}
