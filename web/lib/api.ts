import type { AskResult, DraftView, Explainer, Preview, QueueItem, Source, TicketView, WeeklyLatest, WeeklySummary } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

/** Public API call: JSON in/out; a non-2xx response throws ApiError with FastAPI's `detail`. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server — check your connection and try again.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body?.detail;
    throw new ApiError(res.status, typeof d === "string" ? d : `Request failed (${res.status})`);
  }
  return body as T;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const preview = (text: string) => api<Preview>("/api/ask/preview", post({ text }));
export const ask = (b: { text: string; scheme_id?: string | null; channel?: "text" | "voice" }) =>
  api<AskResult>("/api/ask", post(b));
export const ticket = (code: string) => api<TicketView>(`/api/tickets/${encodeURIComponent(code)}`);
export function transcribe(blob: Blob, durationMs: number): Promise<Preview> {
  const fd = new FormData();
  const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  fd.append("audio", blob, `question.${ext}`);
  fd.append("duration_ms", String(Math.round(durationMs)));
  return api<Preview>("/api/voice/transcribe", { method: "POST", body: fd });
}
export const weeklySummary = () => api<WeeklySummary>("/api/weekly/summary");

// The page's approval desk (Plan 3c): open routes, every click audited as "page".
type Status = { id: number; status: string; error?: string | null };
const enc = encodeURIComponent;
export const deskQueue = () => api<QueueItem[]>("/api/desk/queue");
/** `reply` is the draft text the person saw; the server refuses if it changed meanwhile. */
export const approve = (id: number, reply?: string) =>
  api<Status>(`/api/desk/actions/${id}/approve`, post(reply === undefined ? undefined : { reply }));
export const reject = (id: number) => api<Status>(`/api/desk/actions/${id}/reject`, post());
export const retry = (id: number) => api<Status>(`/api/desk/actions/${id}/retry`, post());
export const editDraft = (id: number, reply: string) => api<DraftView>(`/api/desk/drafts/${id}/edit`, post({ reply }));
export const reprocess = (code: string) => api<{ code: string; status: string }>(`/api/desk/tickets/${enc(code)}/reprocess`, post());
export const weeklyLatest = () => api<WeeklyLatest>("/api/desk/weekly/latest");
export const weeklyRun = () => api<{ status: string; run_id: number }>("/api/desk/weekly/run", post());
export const sources = () => api<Source[]>("/api/desk/sources");
export const explainers = () => api<Explainer[]>("/api/desk/explainers");
