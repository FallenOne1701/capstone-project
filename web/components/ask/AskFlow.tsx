"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, ask, preview as fetchPreview, transcribe } from "@/lib/api";
import { STT_FAIL } from "@/lib/labels";
import type { Recording } from "@/lib/recorder";
import type { Preview } from "@/lib/types";
import { ConfirmCard } from "./ConfirmCard";
import { MicButton } from "./MicButton";

const MAX_CHARS = 500;
type Phase = "compose" | "transcribing" | "confirm" | "submitting";

function message(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong — please try again.";
}

export function AskFlow() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("compose");
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<"text" | "voice">("text");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      router.push(`/t/${r.code}`);
    } catch (err) {
      setError(message(err));
      setPhase("confirm");
    }
  }

  if (preview && (phase === "confirm" || phase === "submitting")) {
    return (
      <div className="space-y-3">
        <ConfirmCard
          preview={preview}
          chosen={chosen}
          onChoose={setChosen}
          onEdit={() => setPhase("compose")}
          onSend={onSend}
          sending={phase === "submitting"}
          extraAction={
            channel === "voice" ? (
              <button
                type="button"
                onClick={() => { setPreview(null); setText(""); setPhase("compose"); }}
                className="rounded-md border border-border-strong px-4 py-2 text-sm"
              >
                Re-record
              </button>
            ) : null
          }
        />
        {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <MicButton
        disabled={phase === "transcribing" || busy}
        onRecorded={onRecorded}
        onError={(m) => setError(m)}
      />
      {phase === "transcribing" && <p className="text-sm text-text-secondary" aria-live="polite">Listening to your question…</p>}
      <form onSubmit={onContinue} className="space-y-3">
        <label htmlFor="question" className="block text-sm font-medium">Your question</label>
        <textarea
          id="question"
          value={text}
          maxLength={MAX_CHARS}
          rows={4}
          onChange={(e) => {
            setText(e.target.value);
            setPreview(null); // edited after confirm → understand it again
          }}
          placeholder="e.g. What is the exit load of HDFC Mid Cap Fund?"
          className="w-full resize-y rounded-lg border border-border-strong bg-surface-panel p-3 text-base"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-text-tertiary" aria-live="polite">{text.length}/{MAX_CHARS}</span>
          <button
            type="submit"
            disabled={!text.trim() || busy || phase === "transcribing"}
            className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Checking…" : "Continue"}
          </button>
        </div>
      </form>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
    </div>
  );
}
