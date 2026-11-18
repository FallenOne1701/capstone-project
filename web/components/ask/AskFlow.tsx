"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, ask, preview as fetchPreview } from "@/lib/api";
import type { Preview } from "@/lib/types";
import { ConfirmCard } from "./ConfirmCard";

const MAX_CHARS = 500;
type Phase = "compose" | "confirm" | "submitting";

export function AskFlow() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("compose");
  const [text, setText] = useState("");
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
      setPhase("confirm");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong — please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function onSend() {
    if (!preview || phase === "submitting") return;
    setPhase("submitting");
    setError(null);
    try {
      const r = await ask({ text, scheme_id: chosen, channel: "text" });
      router.push(`/t/${r.code}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong — please try again.");
      setPhase("confirm");
    }
  }

  if (preview && phase !== "compose") {
    return (
      <div className="space-y-3">
        <ConfirmCard
          preview={preview}
          chosen={chosen}
          onChoose={setChosen}
          onEdit={() => setPhase("compose")}
          onSend={onSend}
          sending={phase === "submitting"}
        />
        {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
      </div>
    );
  }

  return (
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
          disabled={!text.trim() || busy}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Checking…" : "Continue"}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
    </form>
  );
}
