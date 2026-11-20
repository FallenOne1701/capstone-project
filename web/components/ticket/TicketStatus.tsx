"use client";

import { useEffect, useRef, useState } from "react";
import { ScopeNotice } from "@/components/ask/ScopeNotice";
import { ChecksPanel } from "./ChecksPanel";
import { ApiError, ticket as fetchTicket } from "@/lib/api";
import { ASK_AGAIN, CLOSED_TEXT, nextPollMs, progressSteps, scopeNotice, waitingText } from "@/lib/labels";
import { loadVoices, planSpeech, speechLang } from "@/lib/speech";
import { useClientValue } from "@/lib/useClient";
import type { TicketView } from "@/lib/types";

const POLL_MS = 3000;
const URL_RE = /(https?:\/\/[^\s)]+)/g;

function Linkified({ text }: { text: string }) {
  return (
    <>
      {text.split(URL_RE).map((p, i) =>
        /^https?:\/\//.test(p) ? (
          <a key={i} href={p} target="_blank" rel="noreferrer" className="break-all text-primary underline">{p}</a>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

function Progress({ status, approval }: { status: string; approval: "auto" | "person" }) {
  const steps = progressSteps(status, approval);
  if (!steps) return null;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">Progress</p>
      <ol aria-label="Ticket progress" className="mt-3 grid grid-cols-4 gap-1">
        {steps.map((s, i) => (
          <li key={s.label} className="relative flex flex-col items-center text-center" aria-current={s.state === "current" ? "step" : undefined}>
            {i > 0 && (
              <span
                aria-hidden
                className={`absolute top-3 right-1/2 h-0.5 w-full ${s.state === "todo" ? "bg-border-subtle" : "bg-primary"}`}
              />
            )}
            <span
              aria-hidden
              className={`relative flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                s.state === "done"
                  ? "bg-primary text-on-primary"
                  : s.state === "current"
                    ? "bg-surface-panel text-primary ring-2 ring-primary motion-safe:animate-pulse"
                    : "bg-surface-bg text-text-tertiary ring-1 ring-border-strong"
              }`}
            >
              {s.state === "done" ? "✓" : i + 1}
            </span>
            <span className={`mt-1.5 text-xs ${s.state === "todo" ? "text-text-tertiary" : "font-medium text-text-primary"}`}>
              {s.label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface ListenProps { text: string; englishText: string; lang: "en-IN" | "hi-IN"; onFallback: () => void }

function Listen({ text, englishText, lang, onFallback }: ListenProps) {
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const supported = useClientValue(() => "speechSynthesis" in window, false);

  // Load voices up front: iOS only speaks when speak() runs inside the tap itself, not after an await.
  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    let alive = true;
    void loadVoices(synth).then((v) => alive && setVoices(v));
    return () => {
      alive = false;
      synth.cancel(); // leaving the page stops the reading
    };
  }, []);
  if (!supported) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const plan = planSpeech(voices.length ? voices : synth.getVoices(), lang, text, englishText);
    if (plan.fellBack) onFallback(); // no Hindi voice: the page switches to the English text being read
    const u = new SpeechSynthesisUtterance(plan.text);
    u.lang = plan.voice?.lang ?? plan.lang;
    if (plan.voice) u.voice = plan.voice;
    u.onend = u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  }

  return (
    <button type="button" onClick={toggle} className="rounded-md border border-primary px-3 py-1.5 text-sm font-medium text-primary">
      <span aria-hidden>🔊</span> {speaking ? "Stop" : "Listen"}
    </button>
  );
}

export function TicketStatus({ code, onAskAgain }: { code: string; onAskAgain?: (question: string) => void }) {
  const [t, setT] = useState<TicketView | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [english, setEnglish] = useState(false);
  const [noHindiVoice, setNoHindiVoice] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const next = await fetchTicket(code);
        if (!alive) return;
        setT(next);
        setError(null);
        const wait = nextPollMs(next.status);
        if (wait === null) return;
        timer.current = setTimeout(poll, wait);
        return;
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setMissing(true);
          return;
        }
        setError("We can't reach the server right now — we'll keep trying.");
      }
      timer.current = setTimeout(poll, POLL_MS);
    }
    poll();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [code]);

  if (missing) return <p className="text-text-secondary">We couldn&apos;t find that ticket.</p>;
  if (!t) return <p className="text-text-secondary" aria-live="polite">Loading…</p>;

  const local = t.answer_local && !english ? t.answer_local : null;
  const shown = local ? local.text : t.answer;
  const lang = speechLang(t.language, !!local);

  return (
    <div className="space-y-5">
      <Progress status={t.status} approval={t.approval ?? "person"} />
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Your question</p>
        <p className="mt-1 text-text-primary">{t.question}</p>
      </div>
      {scopeNotice(t.intent) && <ScopeNotice text={scopeNotice(t.intent)!} />}

      {t.status === "received" && <p className="text-sm text-text-secondary">We&apos;ve got your question and are preparing an answer.</p>}
      {t.status === "in_review" && (
        <p className="text-sm text-text-secondary" aria-live="polite">{waitingText(t.status, t.approval ?? "person")}</p>
      )}
      {t.status === "closed" && (
        <section aria-label="Not answered" className="flex gap-3 rounded-xl border border-state-danger-border bg-surface-panel p-4">
          <span aria-hidden className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-state-danger-bg font-bold text-state-danger-text ring-1 ring-state-danger-border">!</span>
          <div className="space-y-3">
            <p className="font-semibold text-text-primary">{CLOSED_TEXT}</p>
            {onAskAgain && (
              <button
                type="button"
                onClick={() => onAskAgain(t.question)}
                className="rounded-lg border border-state-pass-border bg-state-pass-bg px-4 py-2 text-sm font-semibold text-primary"
              >
                {ASK_AGAIN}
              </button>
            )}
          </div>
        </section>
      )}
      {t.status === "failed" && (
        <p className="text-sm text-state-danger-text">Something went wrong on our side — our team can see this ticket.</p>
      )}

      {t.status === "answered" && shown && (
        <section aria-label="Answer" className="rounded-xl border border-state-pass-border bg-state-pass-bg p-5">
          <p lang={local ? "hi" : "en"} className="whitespace-pre-line leading-relaxed text-text-primary">
            <Linkified text={shown} />
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Listen
              text={shown}
              englishText={t.answer ?? shown}
              lang={lang}
              onFallback={() => {
                setNoHindiVoice(true);
                setEnglish(true);
              }}
            />
            {t.answer_local && (
              <button type="button" onClick={() => { window.speechSynthesis?.cancel(); setEnglish((e) => !e); }} className="text-sm text-primary underline">
                {english ? "Show Hindi" : "Show English"}
              </button>
            )}
          </div>
          {t.checks && <ChecksPanel checks={t.checks} />}
          {noHindiVoice && (
            <p className="mt-2 text-sm text-text-secondary">No Hindi voice on this device — reading in English.</p>
          )}
        </section>
      )}
      {error && <p role="status" className="text-sm text-state-warn-text">{error}</p>}
    </div>
  );
}
