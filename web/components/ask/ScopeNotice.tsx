import { SCOPE_NOTICE } from "@/lib/labels";

export function ScopeNotice() {
  return (
    <div role="note" className="rounded-lg border border-state-warn-border bg-state-warn-bg px-4 py-3 text-sm text-state-warn-text">
      <p className="font-medium">{SCOPE_NOTICE}</p>
      <p className="mt-1">You can still send it — a person will reply with the facts we can share.</p>
    </div>
  );
}
