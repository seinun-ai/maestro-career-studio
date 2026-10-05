"use client";

import { useEffect, useRef, useState } from "react";

const KEY = "cs-inbox-last-visit";
const DAY_MS = 24 * 60 * 60 * 1000;

/** The previous inbox visit, or the last day if storage is absent or blocked. Null until mounted. */
export function useInboxVisit(): string | null {
  const [since, setSince] = useState<string | null>(null);
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(KEY);
    } catch {
      // Storage blocked: fall back to the last day.
    }
    const valid = stored && !Number.isNaN(Date.parse(stored)) ? stored : null;
    setSince(valid ?? new Date(Date.now() - DAY_MS).toISOString());
    try {
      window.localStorage.setItem(KEY, new Date().toISOString());
    } catch {
      // Remembering a visit is optional; the dashboard still works.
    }
  }, []);
  return since;
}
