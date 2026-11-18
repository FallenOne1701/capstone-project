import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** Loads `fetcher` now and every `ms` (0 = once). `reload()` refreshes on demand, e.g. after an action. */
export function usePoll<T>(fetcher: () => Promise<T>, ms: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fn = useRef(fetcher);
  useEffect(() => {
    fn.current = fetcher;
  });

  const reload = useCallback(async () => {
    try {
      setData(await fn.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (alive) await reload();
    };
    void run();
    const id = ms > 0 ? setInterval(run, ms) : null;
    return () => {
      alive = false;
      if (id) clearInterval(id);
    };
  }, [reload, ms, fetcher]); // a new fetcher (e.g. another filter tab) loads at once

  return { data, error, reload };
}
