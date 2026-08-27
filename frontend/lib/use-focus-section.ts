"use client";

import { useCallback, useEffect } from "react";

const RING = ["ring-2", "ring-primary/60", "rounded-lg"];
/** How long a cross-page landing waits for its target to mount. */
const WAIT_MS = 3000;
/** How long after that to keep the target centred while the page settles. */
const SETTLE_MS = 1200;

function ring(el: HTMLElement) {
  el.classList.add(...RING);
  window.setTimeout(() => el.classList.remove(...RING), 1600);
}

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
    ring(el);
  }, []);

  // A cross-page navigation lands here with a hash; make it behave identically
  // to an in-page focus so the two are indistinguishable to the user.
  //
  // This used to be one `setTimeout(..., 100)`, which lost both halves of the
  // race on a cold load:
  //
  // 1. **The target may not exist yet.** Anchors inside a card BODY — the
  //    `autofill-<group>` fieldsets that `setup-steps.ts` and the job
  //    knock-out card aim at — only mount once the card's queries resolve.
  //    At 100ms the body is still a skeleton, `getElementById` returns null,
  //    and the old code silently gave up. Poll until it appears instead.
  //
  // 2. **Landing is not staying.** Cards ABOVE the target swap their own
  //    skeletons for real content moments later, each swap growing the page
  //    and pushing the target off screen — `#autofill` scrolled correctly and
  //    then ended up ~4000px above the viewport. So hold it centred until the
  //    layout stops changing.
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (!hash) return;

    let cancelled = false;
    let observer: ResizeObserver | null = null;
    const timers: number[] = [];
    const started = performance.now();

    const hold = (el: HTMLElement) => {
      observer = new ResizeObserver(() => {
        if (!cancelled) el.scrollIntoView({ behavior: "auto", block: "center" });
      });
      observer.observe(document.body);
      timers.push(
        window.setTimeout(() => {
          observer?.disconnect();
          observer = null;
        }, SETTLE_MS),
      );
    };

    const poll = window.setInterval(() => {
      if (cancelled) return;
      const el = document.getElementById(hash);
      if (el) {
        window.clearInterval(poll);
        // Instant, not smooth: a smooth scroll animates over the same window
        // in which `hold` is correcting position, and the two fight visibly.
        el.scrollIntoView({ behavior: "auto", block: "center" });
        ring(el);
        hold(el);
        return;
      }
      if (performance.now() - started > WAIT_MS) window.clearInterval(poll);
    }, 50);
    timers.push(poll);

    return () => {
      cancelled = true;
      observer?.disconnect();
      for (const id of timers) {
        window.clearTimeout(id);
        window.clearInterval(id);
      }
    };
  }, []);

  return focus;
}

export default useFocusSection;
