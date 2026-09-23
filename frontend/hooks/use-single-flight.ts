"use client";

import { useRef } from "react";

/**
 * A mutation's `mutate` that starts one request per gesture. `isPending` cannot guard a double click:
 * react-query notifies its observers on a zero-delay timeout, so a second click already queued runs
 * before the re-render that disables the button, reads `isPending === false`, and POSTs again (two
 * referral rows). The ref flips inside the first handler and clears when the request settles.
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
