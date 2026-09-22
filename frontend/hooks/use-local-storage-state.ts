"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

// Same-document writes notify here; other tabs arrive as `storage` events.
const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage disabled: behave as "never set"
  }
}

/**
 * A preference persisted in localStorage and read DURING render. The server
 * and hydration snapshot is null, so `parse(null)` is the default; a component
 * that mounts after hydration paints the stored value on its first frame. The
 * read-in-an-effect pattern this replaces painted the default first.
 * Pass a module-level `parse`/`serialize` so the parsed value is memoised.
 */
export function useLocalStorageState<T>(
  key: string,
  parse: (raw: string | null) => T,
  serialize: (value: T) => string,
): readonly [T, (next: T) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  const value = useMemo(() => parse(raw), [parse, raw]);
  const set = useCallback(
    (next: T) => {
      try {
        window.localStorage.setItem(key, serialize(next));
      } catch {
        // Quota or disabled storage: the preference just doesn't persist.
      }
      listeners.forEach((notify) => notify());
    },
    [key, serialize],
  );
  return [value, set] as const;
}

export const parseFlag = (raw: string | null) => raw === "1";
export const serializeFlag = (value: boolean) => (value ? "1" : "0");
