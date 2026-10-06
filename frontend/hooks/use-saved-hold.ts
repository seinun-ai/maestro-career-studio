"use client";

import { useEffect, useState } from "react";

import { CONFIRM_HOLD_MS } from "@/lib/motion";

/** True for CONFIRM_HOLD_MS after `pending` falls with no failure. State, not a ref: the
 *  previous `pending` is compared during render, which the compiler forbids for refs. */
export function useSavedHold(pending: boolean, failed: boolean): boolean {
  const [prevPending, setPrevPending] = useState(pending);
  const [held, setHeld] = useState(false);
  if (pending !== prevPending) {
    setPrevPending(pending);
    setHeld(prevPending && !pending && !failed);
  }
  useEffect(() => {
    if (!held) return;
    const timer = window.setTimeout(() => setHeld(false), CONFIRM_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [held]);
  return held;
}
