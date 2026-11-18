"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/console", label: "Queue" },
  { href: "/console/pulse", label: "Pulse" },
  { href: "/console/approvals", label: "Approvals" },
  { href: "/console/explainers", label: "Explainers" },
  { href: "/console/sources", label: "Sources" },
];

export function Nav({ onSignOut }: { onSignOut: () => void }) {
  const path = usePathname();
  return (
    <header className="border-b border-border-subtle bg-surface-panel">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <span className="font-headline font-semibold text-primary">Support console</span>
        <nav aria-label="Console" className="flex flex-1 flex-wrap gap-1">
          {LINKS.map((l) => {
            const active = path === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm ${active ? "bg-state-pass-bg font-medium text-state-pass-text" : "text-text-secondary hover:text-text-primary"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <button type="button" onClick={onSignOut} className="text-sm text-text-secondary underline">Sign out</button>
      </div>
    </header>
  );
}
