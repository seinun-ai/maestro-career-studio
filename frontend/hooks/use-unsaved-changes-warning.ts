"use client";

import { useEffect } from "react";

/**
 * Warn before the browser discards unsaved editor state.
 *
 * Neither resume studio had any guard at all — `grep beforeunload` over the
 * whole repo returned nothing. Both track a dirty flag already (`editor-body`'s
 * `hasUnsavedChanges`, the tailored studio's `dirty`), but it was only ever used
 * to gate a button, so a reload, a closed tab, or a typed URL took the edits
 * with it silently.
 *
 * This covers the BROWSER-level exits only: reload, close, and navigation away
 * from the origin. It cannot intercept an in-app `<Link>` click, because the
 * App Router gives no navigation-blocking hook — that gap is real and is why
 * the studios should keep their explicit Save affordance rather than relying on
 * this. Guarding the common accidental exit is still worth it; the alternative
 * was guarding nothing.
 *
 * `preventDefault()` plus assigning `returnValue` is the spec-compliant pair —
 * Chrome and Safari honour the former, older Firefox the latter. The browser
 * shows its own wording; a custom message has been ignored for a decade.
 */
export function useUnsavedChangesWarning(when: boolean) {
  useEffect(() => {
    if (!when) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [when]);
}
