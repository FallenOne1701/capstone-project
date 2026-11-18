"use client";

import { useState, useSyncExternalStore } from "react";
import { ApiError, checkKey } from "@/lib/api";
import { clearKey, getKey, setKey, subscribeKey } from "@/lib/session";
import { Nav } from "./Nav";

export function ConsoleGate({ children }: { children: React.ReactNode }) {
  // undefined during SSR/hydration, then the tab's stored key (or null)
  const key = useSyncExternalStore(subscribeKey, getKey, () => undefined);
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (key === undefined) return null;

  if (!key) {
    async function signIn(e: React.FormEvent) {
      e.preventDefault();
      setBusy(true);
      setError(null);
      try {
        if (await checkKey(pw)) {
          setKey(pw);
          setPw("");
        } else {
          setError("Wrong password");
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Can't reach the server.");
      } finally {
        setBusy(false);
      }
    }
    return (
      <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 py-16">
        <h1 className="font-headline text-xl font-semibold">Support console</h1>
        <p className="mt-1 text-sm text-text-secondary">For the Groww support team. Nothing is sent without your approval.</p>
        <form onSubmit={signIn} className="mt-6 space-y-3">
          <label htmlFor="console-password" className="block text-sm font-medium">Console password</label>
          <input
            id="console-password"
            type="password"
            autoComplete="current-password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="w-full rounded-md border border-border-strong bg-surface-panel px-3 py-2"
          />
          {error && <p role="alert" className="text-sm text-state-danger-text">{error}</p>}
          <button
            type="submit"
            disabled={!pw || busy}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
          >
            {busy ? "Checking…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <>
      <Nav onSignOut={clearKey} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
