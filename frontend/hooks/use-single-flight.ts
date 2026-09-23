"use client";

import { useRef } from "react";

/**
 * A mutation's `mutate` that starts one request per gesture. `isPending` cannot guard a double click:
 * react-query notifies its observers on a zero-delay timeout, so a second click already queued runs
 * before the re-render that disables the button, reads `isPending === false`, and POSTs again (two
 * referral rows). The ref flips inside the first handler and clears when the request settles.
 *
 * It clears through the per-call `onSettled`, which react-query drops when the mutation is `.reset()`
 * or when another `.mutate(...)` on the same mutation starts while this one runs (only the latest
 * call's callbacks fire). Either leaves the guard shut for good, so a guarded mutation is started
 * only through this function and never reset while it runs.
 */
export function useSingleFlight<TVars>(
  mutate: (vars: TVars, options?: { onSettled?: () => void }) => void,
): (vars: TVars) => void {
  const inFlight = useRef(false);
  return (vars) => {
    if (inFlight.current) return;
    inFlight.current = true;
    mutate(vars, { onSettled: () => { inFlight.current = false; } });
  };
}
