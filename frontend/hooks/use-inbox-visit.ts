"use client";

import { useEffect, useRef, useState } from "react";
import { createVisitClock } from "@/lib/inbox-visit";

const VISIT_CLOCK = createVisitClock();

/** The tab's previous inbox visit, kept through remounts until reload. Null until mounted. */
export function useInboxVisit(): string | null {
  const [since, setSince] = useState<string | null>(null);
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    let storage: Storage | null = null;
    try {
      storage = window.localStorage;
    } catch {
      // Some browsers block access to the storage object itself.
    }
    setSince(VISIT_CLOCK.resolve(storage, Date.now()));
  }, []);
  return since;
}
