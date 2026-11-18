import { useCallback, useEffect, useRef, useState } from "react";

export const MAX_MS = 60_000;
export const MIN_MS = 1_000;

const MIME_ORDER = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

/** First recording format this browser supports (Safari/iOS has no webm → mp4). */
export function pickMimeType(isSupported: (t: string) => boolean): string | null {
  return MIME_ORDER.find((t) => isSupported(t)) ?? null;
}

export type VoiceSupport = "ok" | "insecure" | "unsupported";

export function voiceSupport(env: { secure: boolean; hasMediaDevices: boolean; hasRecorder: boolean }): VoiceSupport {
  if (!env.secure) return "insecure";
  if (!env.hasMediaDevices || !env.hasRecorder) return "unsupported";
  return "ok";
}

export function browserVoiceSupport(): VoiceSupport {
  if (typeof window === "undefined") return "unsupported";
  return voiceSupport({
    secure: window.isSecureContext,
    hasMediaDevices: !!navigator.mediaDevices?.getUserMedia,
    hasRecorder: typeof MediaRecorder !== "undefined",
  });
}

export function formatClock(ms: number): string {
  const s = Math.min(Math.floor(ms / 1000), 599);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export type RecorderState = "idle" | "recording" | "denied" | "error";
export interface Recording { blob: Blob; durationMs: number }

/**
 * Microphone recording held in memory only. Stops itself at MAX_MS (the result goes to onAutoStop)
 * and always releases the microphone on stop and on unmount.
 */
export function useRecorder(onAutoStop?: (r: Recording | null) => void) {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsedMs, setElapsed] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const tick = useRef<ReturnType<typeof setInterval> | null>(null);
  const cap = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoStop = useRef(onAutoStop);
  useEffect(() => {
    autoStop.current = onAutoStop;
  });

  const release = useCallback(() => {
    if (tick.current) clearInterval(tick.current);
    if (cap.current) clearTimeout(cap.current);
    tick.current = cap.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const stop = useCallback((): Promise<Recording | null> => {
    const r = rec.current;
    if (!r || r.state === "inactive") {
      release();
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      r.onstop = () => {
        const durationMs = Date.now() - startedAt.current;
        const blob = new Blob(chunks.current, { type: r.mimeType || "audio/webm" });
        chunks.current = [];
        rec.current = null;
        release();
        setState("idle");
        resolve(blob.size ? { blob, durationMs } : null);
      };
      r.stop();
    });
  }, [release]);

  const start = useCallback(async () => {
    if (rec.current) return;
    const mime = pickMimeType((t) => MediaRecorder.isTypeSupported(t));
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name;
      setState(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "error");
      return;
    }
    try {
      const r = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      r.ondataavailable = (ev) => ev.data.size && chunks.current.push(ev.data);
      rec.current = r;
      startedAt.current = Date.now();
      setElapsed(0);
      r.start(250);
      setState("recording");
      tick.current = setInterval(() => setElapsed(Date.now() - startedAt.current), 200);
      cap.current = setTimeout(() => {
        void stop().then((res) => autoStop.current?.(res));
      }, MAX_MS);
    } catch {
      release();
      setState("error");
    }
  }, [release, stop]);

  useEffect(() => () => {
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
    rec.current = null;
    chunks.current = [];
    release();
  }, [release]);

  return { state, elapsedMs, start, stop };
}
