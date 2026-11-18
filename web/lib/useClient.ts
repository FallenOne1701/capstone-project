import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** A browser-only value (e.g. feature support): `serverValue` during SSR/hydration, then the real one. */
export function useClientValue<T>(get: () => T, serverValue: T): T {
  return useSyncExternalStore(noop, get, () => serverValue);
}
