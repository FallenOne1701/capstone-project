"use client";

import { useEffect, useState } from "react";
import { ApiError, ask, preview as fetchPreview, transcribe } from "@/lib/api";
import { STT_FAIL } from "@/lib/labels";
import type { Recording } from "@/lib/recorder";
import type { Preview } from "@/lib/types";
import { TicketStatus } from "@/components/ticket/TicketStatus";
import { ConfirmCard } from "./ConfirmCard";
import { HowItWorks } from "./HowItWorks";
import { MicButton } from "./MicButton";

const MAX_CHARS = 500;
type Phase = "compose" | "transcribing" | "confirm" | "submitting";

function message(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong — please try again.";
}

export function AskFlow({ initialCode = null, onCode }: { initialCode?: string | null; onCode?: (code: string | null) => void }) {
  const [code, setCode] = useState<string | null>(initialCode);
  const [phase, setPhase] = useState<Phase>("compose");
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<"text" | "voice">("text");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // the desk keeps the open ticket in the address (?t=CODE), so a reload or shared link shows it
  useEffect(() => {
    onCode?.(code);
  }, [code, onCode]);

  async function onContinue(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await fetchPreview(text));
      setChosen(null);
      setChannel("text");
      setPhase("confirm");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRecorded(rec: Recording) {
    setPhase("transcribing");
    setError(null);
    try {
      // the clip goes straight to the server and is dropped here; only the redacted transcript comes back
      const p = await transcribe(rec.blob, rec.durationMs);
      setPreview(p);
      setText(p.redacted_text);
      setChosen(null);
      setChannel("voice");
      setPhase("confirm");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 422 ? STT_FAIL : message(err));
      setPhase("compose");
    }
  }

  async function onSend() {
    if (!preview || phase === "submitting") return;
    setPhase("submitting");
    setError(null);
    try {
      const r = await ask({ text, scheme_id: chosen, channel });
      // the ticket opens on the right; the box clears for the next question
      setCode(r.code);
      setText("");
      setPreview(null);
      setChosen(null);
      setPhase("compose");
    } catch (err) {
      setError(message(err));
      setPhase("confirm");
    }
  }

  function edit(next: string) {
    setText(next);
    setPreview(null); // changed text is understood again on Continue
    setPhase("compose");
  }

  const confirming = !!preview && (phase === "confirm" || phase === "submitting");

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-6">
        <form onSubmit={onContinue} className="rounded-xl border border-border-subtle bg-surface-panel p-6 shadow-sm">
          <label htmlFor="question" className="block text-xs font-semibold uppercase tracking-wide text-text-tertiary">
            Your question
          </label>
          <textarea
            id="question"
            value={text}
            maxLength={MAX_CHARS}
            rows={4}
            onChange={(e) => edit(e.target.value)}
            placeholder="e.g. What is the exit load of HDFC Mid Cap Fund?"
            className="mt-2 w-full resize-y rounded-lg border border-border-subtle bg-surface-panel p-3 text-base leading-relaxed"
          />
          <div className="mt-3 border-t border-border-subtle pt-4">
            <MicButton
              disabled={phase === "transcribing" || busy}
              onRecorded={onRecorded}
              onError={(m) => setError(m)}
            />
            {phase === "transcribing" && (
              <p className="mt-2 text-sm text-text-secondary" aria-live="polite">Listening to your question…</p>
            )}
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="font-mono-token text-xs text-text-tertiary" aria-live="polite">{text.length} / {MAX_CHARS}</span>
              <button
                type="submit"
                disabled={!text.trim() || busy || phase === "transcribing"}
                className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "Checking…" : "Continue"}
              </button>
            </div>
          </div>
        </form>

        {confirming && preview && (
          <div className="rounded-xl border border-border-subtle bg-surface-panel p-6 shadow-sm">
            <ConfirmCard
              preview={preview}
              chosen={chosen}
              onChoose={setChosen}
              onEdit={() => edit(text)}
              onSend={onSend}
              sending={phase === "submitting"}
              extraAction={
                channel === "voice" ? (
                  <button
                    type="button"
                    onClick={() => edit("")}
                    className="rounded-md border border-border-strong px-4 py-2 text-sm"
                  >
                    Re-record
                  </button>
                ) : null
              }
            />
          </div>
        )}
        {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      </div>

      <div className="min-w-0">
        {code ? (
          <div className="rounded-xl border border-border-subtle bg-surface-panel p-6 shadow-sm">
            <p className="text-xs text-text-tertiary">Ticket</p>
            <p className="mt-1 inline-block rounded-md bg-surface-bg px-2 py-1 font-mono-token text-sm font-semibold ring-1 ring-border-subtle">
              {code}
            </p>
            <div className="mt-5 border-t border-border-subtle pt-5">
              <TicketStatus
                code={code}
                onAskAgain={(question) => {
                  // the closed ticket's question goes back in the box to reword
                  setCode(null);
                  edit(question);
                }}
              />
            </div>
          </div>
        ) : (
          <HowItWorks onPick={edit} />
        )}
      </div>
    </div>
  );
}
