"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/** Run an async loader on mount and whenever `deps` change. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loaderRef
      .current()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Call `fn` every `intervalMs` while `enabled` (the ticket screen uses 2000 in Phase 13). */
export function usePolling(fn: () => void | Promise<void>, intervalMs: number, enabled = true): void {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => void fnRef.current(), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}

/** Debounce a fast-changing value such as a search box. */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
