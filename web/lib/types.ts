// Mirrors the API's JSON. Keep in step with api/app/api/{public,console,desk}.py.

export type Intent =
  | "fee_question" | "fund_fact" | "how_to_process" | "advice_request"
  | "performance_request" | "account_issue" | "out_of_scope";
export type Language = "en" | "hi" | "hinglish";
export type TicketStatus = "received" | "in_review" | "answered" | "failed" | "closed";

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
  approval: "auto" | "person";
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

export interface WeeklySummary {
  week_ending: string;
  window_start: string | null;
  window_end: string | null;
  stale: boolean;
  review_count: number | null;
  themes: { label: string; count: number; recent_count: number }[];
  quotes: { text: string; theme: string | null }[];
  repeated: { label: string; count: number }[];
  explainer: { title: string; bullets: { text: string; url: string }[]; last_checked: string } | null;
  delivery: { doc: string; email_draft: string };
}
export interface ReviewFailure { check: string; detail?: string; [k: string]: unknown }

export interface DraftView {
  id: number;
  reply: string;
  citation: string | null;
  last_checked: string | null;
  disposition: string;
  routing: { team: string; priority: string; why: string };
  review_status: "pass" | "fail" | "blocked";
  review_failures: ReviewFailure[];
  searched: string[];
  reused_explainer_id: number | null;
  edited: boolean;
  translation: LocalText | null;
  /** a Hindi/Hinglish draft whose translation is still being made */
  translation_pending?: boolean;
}

export type ActionStatus = "pending" | "approved" | "executed" | "failed" | "rejected";

export interface QueueItem {
  code: string;
  status: TicketStatus;
  intent: Intent | null;
  language: Language;
  question: string;
  pii_types: string[];
  created_at: string;
  draft: DraftView | null;
  action: { id: number; status: ActionStatus; target: string; error: string | null } | null;
}

export interface Action {
  id: number;
  type: "reply_publish" | "doc_append" | "email_draft";
  status: ActionStatus;
  target_label: string;
  content: string | null;
  source_ref: string | null;
  error: string | null;
  created_at: string;
  decided_at: string | null;
  executed_at: string | null;
}

export interface Bullet { text: string; url: string }

export interface Explainer {
  id: number;
  topic: string;
  title: string;
  bullets: Bullet[];
  last_checked: string;
  status: "draft" | "canonical" | "superseded" | "rejected";
  evidence: Record<string, unknown> | null;
  run_id: number | null;
  canonical_at: string | null;
  reuse_count: number;
}

export interface Theme {
  theme_id: string; label: string; count: number; recent_count: number; review_ids: string[];
  window_start: string; window_end: string; rank: number;
}

export interface Repeated { key?: string; label: string; count: number; window_start: string; window_end: string }

export interface WeeklyLatest {
  run: {
    id: number; status: string; started_at: string | null; finished_at: string | null;
    window_start: string | null; window_end: string | null; review_count: number | null;
    pulse_text: string | null; error: string | null; llm_calls: number | null;
  };
  themes: Theme[];
  repeated: Repeated[];
  actions: Action[];
  explainer: Explainer | null;
  /** the newest run, which may still be running or have failed while `run` is the newest ready one */
  latest_attempt?: { id: number; status: string; error: string | null };
}

export interface Source {
  url: string; title: string; kind: string; status: string;
  last_checked: string | null; error: string | null;
}
