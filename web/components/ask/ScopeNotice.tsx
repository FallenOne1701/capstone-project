import { SCOPE_NOTICE } from "@/lib/labels";

export function ScopeNotice({ text = SCOPE_NOTICE }: { text?: string }) {
  return (
    <div role="note" className="rounded-lg border border-state-warn-border bg-state-warn-bg px-4 py-3 text-sm text-state-warn-text">
      <p className="font-medium">{text}</p>
    </div>
  );
}
