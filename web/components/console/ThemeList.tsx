import type { Theme } from "@/lib/types";

export function ThemeList({ themes }: { themes: Theme[] }) {
  if (!themes.length) return <p className="text-sm text-text-secondary">No themes in this run.</p>;
  return (
    <ol aria-label="Themes" className="space-y-2">
      {themes.map((t) => (
        <li key={t.theme_id} className="rounded-lg border border-border-subtle bg-surface-panel p-3">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <span className="font-mono-token text-xs text-text-tertiary">#{t.rank}</span>
            <span className="font-medium">{t.label}</span>
            <span className="text-sm text-text-secondary">
              {t.count} reviews · {t.recent_count} in last 7 days · {t.window_start} to {t.window_end}
            </span>
          </div>
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-primary">Review ids ({t.review_ids.length})</summary>
            <p className="font-mono-token mt-1 break-words text-xs text-text-secondary">{t.review_ids.join(", ")}</p>
          </details>
        </li>
      ))}
    </ol>
  );
}
