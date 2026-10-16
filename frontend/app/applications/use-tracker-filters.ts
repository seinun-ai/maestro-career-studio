"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  TRACKER_STORE_KEYS,
  resolveTrackerFilters,
  trackerHref,
  type StageFilter,
  type TrackerFilters,
} from "@/lib/tracker-filters";

export function storedValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storeValue(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // Session memory is a convenience — never let storage failures break the page.
  }
}

/**
 * The Jobs list's Status filter, stage chip and source toggle: one state, started by `resolveTrackerFilters`
 * (the URL, else session memory), and one `update` that keeps the URL and session memory in step.
 */
export function useTrackerFilters<F extends string>(filters: readonly F[]) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<TrackerFilters>(() =>
    resolveTrackerFilters((key) => searchParams.get(key), storedValue, filters),
  );

  const update = (partial: Partial<{ filter: F; stage: StageFilter | null; source: TrackerFilters["source"] }>) => {
    const next = { ...state, ...partial };
    setState(next);
    for (const axis of Object.keys(partial) as (keyof TrackerFilters)[]) {
      storeValue(TRACKER_STORE_KEYS[axis], next[axis] ?? "");
    }
    // A filter switch keeps the reader where they are, not at the top.
    router.replace(trackerHref(next), { scroll: false });
  };

  return { filter: state.filter as F, stage: state.stage, source: state.source, update };
}
