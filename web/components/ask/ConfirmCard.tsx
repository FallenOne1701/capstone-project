"use client";

import { Redacted } from "@/components/Redacted";
import { clarifyQuestion, intentLabel, SCOPE_INTENTS } from "@/lib/labels";
import type { Preview } from "@/lib/types";
import { ScopeNotice } from "./ScopeNotice";

interface Props {
  preview: Preview;
  chosen: string | null;
  onChoose: (schemeId: string) => void;
  onEdit: () => void;
  onSend: () => void;
  sending: boolean;
  extraAction?: React.ReactNode;
}

export function ConfirmCard({ preview, chosen, onChoose, onEdit, onSend, sending, extraAction }: Props) {
  const needsChoice = preview.needs_clarification && !chosen;
  const names = preview.scheme_names.length ? preview.scheme_names : preview.options;
  const shown = chosen
    ? { ...preview, scheme_names: [names[preview.scheme_ids.indexOf(chosen)] ?? chosen] }
    : preview;
  return (
    <section aria-label="Check your question" className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">We understood</p>
        <p className="mt-1 text-base leading-relaxed text-text-primary">
          <Redacted text={preview.redacted_text} />
        </p>
        {preview.pii_types.length > 0 && (
          <p className="mt-2 text-xs text-text-secondary">
            Personal details were hidden before anything was saved.
          </p>
        )}
      </div>
      <p className="inline-flex items-center gap-2 rounded-full border border-state-pass-border bg-state-pass-bg px-3 py-1 text-sm font-medium text-state-pass-text">
        <span className="h-2 w-2 rounded-full bg-state-pass-dot" aria-hidden />
        {intentLabel(shown)}
      </p>

      {preview.needs_clarification && (
        <fieldset className="rounded-lg border border-border-subtle p-4">
          <legend className="px-1 text-sm font-medium">{clarifyQuestion(names)}</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {preview.scheme_ids.map((id, i) => (
              <button
                key={id}
                type="button"
                aria-pressed={chosen === id}
                onClick={() => onChoose(id)}
                className={`rounded-md border px-3 py-1.5 text-sm ${
                  chosen === id
                    ? "border-primary bg-primary text-on-primary"
                    : "border-border-strong bg-surface-panel hover:border-primary"
                }`}
              >
                {names[i] ?? id}
              </button>
            ))}
          </div>
        </fieldset>
      )}

      {SCOPE_INTENTS.includes(preview.intent) && <ScopeNotice />}

      <div className="flex flex-wrap items-center gap-3 pt-2">
        <button
          type="button"
          onClick={onSend}
          disabled={needsChoice || sending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? "Sending…" : "Send question"}
        </button>
        <button type="button" onClick={onEdit} className="rounded-md border border-border-strong px-4 py-2 text-sm">
          Edit
        </button>
        {extraAction}
      </div>
    </section>
  );
}
