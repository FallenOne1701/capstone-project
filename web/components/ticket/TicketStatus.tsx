"use client";

import { useEffect, useRef, useState } from "react";
import { ScopeNotice } from "@/components/ask/ScopeNotice";
import { ApiError, ticket as fetchTicket } from "@/lib/api";
import { SCOPE_INTENTS, statusLabel } from "@/lib/labels";
import { loadVoices, pickVoice, speechLang } from "@/lib/speech";
import { useClientValue } from "@/lib/useClient";
import type { TicketView } from "@/lib/types";

const POLL_MS = 3000;
const STEPS = ["received", "in review", "answered"] as const;
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

function Progress({ status }: { status: string }) {
  const word = statusLabel(status);
  const at = STEPS.indexOf(word as (typeof STEPS)[number]);
  return (
    <ol aria-label="Ticket progress" className="flex items-center gap-2 text-sm">
      {STEPS.map((s, i) => {
        const done = at >= i;
        return (
          <li key={s} className="flex items-center gap-2" aria-current={at === i ? "step" : undefined}>
            <span className={`h-2.5 w-2.5 rounded-full ${done ? "bg-state-pass-dot" : "bg-border-strong"}`} aria-hidden />
            <span className={done ? "font-medium text-text-primary" : "text-text-tertiary"}>{s}</span>
            {i < STEPS.length - 1 && <span className={`h-px w-8 ${at > i ? "bg-state-pass-dot" : "bg-border-strong"}`} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

interface ListenProps { text: string; englishText: string; lang: "en-IN" | "hi-IN"; onFallback: () => void }

function Listen({ text, englishText, lang, onFallback }: ListenProps) {
  const [speaking, setSpeaking] = useState(false);
  const supported = useClientValue(() => "speechSynthesis" in window, false);
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, []);
  if (!supported) return null;

  async function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const voices = await loadVoices(synth);
    let { voice, fellBack } = pickVoice(voices, lang);
    let say = text;
    if (fellBack) {
      // no Hindi voice on this device: show and read the English answer instead
      onFallback();
      ({ voice } = pickVoice(voices, "en-IN"));
      say = englishText;
      fellBack = false;
    }
    const u = new SpeechSynthesisUtterance(say);
    u.lang = voice?.lang ?? (say === text ? lang : "en-IN");
    if (voice) u.voice = voice;
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

export function TicketStatus({ code }: { code: string }) {
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
        if (next.status === "answered" || next.status === "failed") return;
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
      <Progress status={t.status} />
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Your question</p>
        <p className="mt-1 text-text-primary">{t.question}</p>
      </div>
      {t.intent && SCOPE_INTENTS.includes(t.intent) && <ScopeNotice />}

      {t.status === "received" && <p className="text-sm text-text-secondary">We&apos;ve got your question and are preparing an answer.</p>}
      {t.status === "in_review" && <p className="text-sm text-text-secondary">A person is checking the answer before it&apos;s sent to you.</p>}
      {t.status === "failed" && (
        <p className="text-sm text-state-danger-text">Something went wrong on our side — our team can see this ticket.</p>
      )}

      {t.status === "answered" && shown && (
        <section aria-label="Answer" className="rounded-lg border border-state-pass-border bg-state-pass-bg p-4">
          <p lang={local ? "hi" : "en"} className="whitespace-pre-line leading-relaxed text-text-primary">
            <Linkified text={shown} />
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Listen
              key={lang}
              text={shown}
              englishText={t.answer ?? shown}
              lang={lang}
              onFallback={() => {
                setNoHindiVoice(true);
                setEnglish(true);
              }}
            />
            {t.answer_local && (
              <button type="button" onClick={() => setEnglish((e) => !e)} className="text-sm text-primary underline">
                {english ? "Show Hindi" : "Show English"}
              </button>
            )}
          </div>
          {noHindiVoice && (
            <p className="mt-2 text-sm text-text-secondary">No Hindi voice on this device — reading in English.</p>
          )}
        </section>
      )}
      {error && <p role="status" className="text-sm text-state-warn-text">{error}</p>}
    </div>
  );
}
