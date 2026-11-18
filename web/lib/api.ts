import type {
  Action, AskResult, DraftView, Explainer, Preview, QueueItem, RefreshResult, Source, TicketView, WeeklyLatest,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const KEY_STORAGE = "consoleKey";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

function readKey(): string | null {
  try {
    return sessionStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

export async function api<T>(path: string, init?: RequestInit, opts?: { console?: boolean; key?: string }): Promise<T> {
  const headers = new Headers(init?.headers);
  if (opts?.console) {
    const key = opts.key ?? readKey();
    if (key) headers.set("X-Console-Key", key);
  }
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
const C = { console: true };

// Public
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

// Console
type Status = { id: number; status: string; error?: string | null };
export const queue = () => api<QueueItem[]>("/api/console/queue", undefined, C);
export const approve = (id: number) => api<Status>(`/api/console/actions/${id}/approve`, post(), C);
export const reject = (id: number) => api<Status>(`/api/console/actions/${id}/reject`, post(), C);
export const retry = (id: number) => api<Status>(`/api/console/actions/${id}/retry`, post(), C);
export const editDraft = (id: number, reply: string) => api<DraftView>(`/api/console/drafts/${id}/edit`, post({ reply }), C);
export const reprocess = (code: string) =>
  api<{ code: string; status: string }>(`/api/console/tickets/${encodeURIComponent(code)}/reprocess`, post(), C);
export const actions = (status?: string) =>
  api<Action[]>(`/api/console/actions${status ? `?status=${encodeURIComponent(status)}` : ""}`, undefined, C);
export const weeklyLatest = () => api<WeeklyLatest>("/api/console/weekly/latest", undefined, C);
export const weeklyRun = () => api<{ status: string; run_id: number }>("/api/console/weekly/run", post(), C);
export const explainers = () => api<Explainer[]>("/api/console/explainers", undefined, C);
export const sources = () => api<Source[]>("/api/console/sources", undefined, C);
export const refreshSources = () => api<RefreshResult>("/api/console/sources/refresh", post(), C);

/** True when the API accepts this console password. */
export async function checkKey(key: string): Promise<boolean> {
  try {
    await api("/api/console/actions?status=pending", undefined, { console: true, key });
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return false;
    throw e;
  }
}
