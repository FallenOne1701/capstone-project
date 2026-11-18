import Link from "next/link";

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-border-subtle bg-surface-panel">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <Link href="/ask" className="font-headline text-base font-semibold text-primary">Groww Support Desk</Link>
          <span className="text-xs text-text-tertiary">Facts only · no advice</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">{children}</main>
    </>
  );
}
