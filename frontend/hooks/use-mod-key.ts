"use client";

import { useSyncExternalStore } from "react";

import { modKeyFor, type ModKey } from "@/lib/shortcuts";

// The platform never changes while the page is open, so there is nothing to
// subscribe to.
function subscribeNoop() {
  return () => {};
}

/**
 * The platform's modifier, for shortcut hints. "Ctrl" on the server AND on the
 * hydration render so the markup matches; React re-renders with the client
 * snapshot straight after.
 */
export function useModKey(): ModKey {
  return useSyncExternalStore(
    subscribeNoop,
    () => modKeyFor(navigator.platform || navigator.userAgent),
    () => "Ctrl",
  );
}
