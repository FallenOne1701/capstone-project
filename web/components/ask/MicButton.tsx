"use client";

import { STT_FAIL } from "@/lib/labels";
import { useClientValue } from "@/lib/useClient";
import { browserVoiceSupport, formatClock, isSilent, MAX_MS, MIN_MS, type Recording, useRecorder, type VoiceSupport } from "@/lib/recorder";

const UNSUPPORTED: Record<Exclude<VoiceSupport, "ok">, string> = {
  insecure: "Voice input needs a secure (https) page — please type your question.",
  unsupported: "This browser can't record audio — please type your question.",
};
const DENIED = "Microphone access is blocked. Allow it in your browser's site settings, or type your question below.";

interface Props {
  disabled?: boolean;
  onRecorded: (r: Recording) => void;
  onError: (message: string) => void;
}

export function MicButton({ disabled, onRecorded, onError }: Props) {
  const support = useClientValue<VoiceSupport | null>(browserVoiceSupport, null);
  const deliver = (r: Recording | null) => {
    if (!r || r.durationMs < MIN_MS || isSilent(r.peak)) onError(STT_FAIL);
    else onRecorded(r);
  };
  const { state, elapsedMs, start, stop } = useRecorder(deliver);

  if (support === null) return null;
  if (support !== "ok") {
    return <p className="text-sm text-text-secondary">{UNSUPPORTED[support]}</p>;
  }

  const recording = state === "recording";
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={disabled}
          aria-label={recording ? "Stop recording" : "Speak your question"}
          onClick={async () => (recording ? deliver(await stop()) : start())}
          className={`flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold disabled:opacity-50 ${
            recording ? "bg-state-danger-dot text-white" : "border border-primary text-primary hover:bg-state-pass-bg"
          }`}
        >
          <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${recording ? "animate-pulse bg-white" : "bg-primary"}`} />
          {recording ? "Stop" : "Speak"}
        </button>
        {recording && (
          <span className="font-mono-token text-sm tabular-nums text-text-secondary" aria-live="off">
            {formatClock(elapsedMs)} / {formatClock(MAX_MS)}
          </span>
        )}
        {!recording && <span className="text-xs text-text-tertiary">English, Hindi or Hinglish · up to 1 minute</span>}
      </div>
      {state === "denied" && <p role="alert" className="text-sm text-state-danger-text">{DENIED}</p>}
      {state === "error" && (
        <p role="alert" className="text-sm text-state-danger-text">
          We couldn&apos;t start the microphone — please type your question.
        </p>
      )}
    </div>
  );
}
