"use client";

import { useCallback, useEffect } from "react";

const RING = ["ring-2", "ring-primary/60", "rounded-lg"];

/** Scroll a section into view and ring it briefly, without navigating. */
export function useFocusSection() {
  const focus = useCallback((anchor: string) => {
    const el = document.getElementById(anchor);
    if (!el) return;
    // Smooth scrolling is compositor-driven, so it never progresses while the
    // document is hidden — a link opened in a background tab would land at the
    // top with nothing focused. Jump instantly in that case; animate when the
    // user is actually watching.
    const behavior: ScrollBehavior =
      document.visibilityState === "visible" ? "smooth" : "auto";
    el.scrollIntoView({ behavior, block: "center" });
    el.classList.add(...RING);
    window.setTimeout(() => el.classList.remove(...RING), 1600);
  }, []);

  // A cross-page navigation lands here with a hash; make it behave identically
  // to an in-page focus so the two are indistinguishable to the user.
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    const id = window.setTimeout(() => focus(hash), 100); // let the section mount
    return () => window.clearTimeout(id);
  }, [focus]);

  return focus;
}

export default useFocusSection;
