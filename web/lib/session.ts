/** Console password for this browser tab only (sessionStorage), observable so the gate re-renders on change. */

export const KEY_STORAGE = "consoleKey";
const listeners = new Set<() => void>();

export function getKey(): string | null {
  try {
    return sessionStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

function emit() {
  listeners.forEach((l) => l());
}

export function setKey(key: string): void {
  try {
    sessionStorage.setItem(KEY_STORAGE, key);
  } catch {
    /* storage blocked: the key lives only until reload */
  }
  emit();
}

export function clearKey(): void {
  try {
    sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    /* ignore */
  }
  emit();
}

export function subscribeKey(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}
