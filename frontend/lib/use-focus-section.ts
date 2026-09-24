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

/** Shown, not merely mounted: a card in a hidden tab panel is in the DOM with no box. */
function shown(anchor: string): HTMLElement | null {
  const el = document.getElementById(anchor);
  return el && el.getClientRects().length > 0 ? el : null;
}

/**
 * Put `anchor` in the address bar with no history entry and no scroll, and tell the page. A tabbed
 * page (Settings, Profile) opens the tab that renders it (`useSettingsTab` listens for hashchange);
 * Next listens for no hashchange, so the synthetic event reaches only that hook.
 */
function announce(anchor: string) {
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}#${anchor}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Poll (every 50ms, up to WAIT_MS) until `anchor` is shown, then hand it over. Returns a cancel. */
function whenShown(anchor: string, then: (el: HTMLElement) => void): () => void {
  const started = performance.now();
  const poll = window.setInterval(() => {
    const el = shown(anchor);
    if (el) {
      window.clearInterval(poll);
      then(el);
      return;
    }
    if (performance.now() - started > WAIT_MS) window.clearInterval(poll);
  }, 50);
  return () => window.clearInterval(poll);
}

/** Scroll a section into view and ring it briefly, without navigating; opens its tab first if hidden. */
export function useFocusSection() {
  const focus = useCallback((anchor: string) => {
    if (!document.getElementById(anchor)) return;
    if (!shown(anchor)) announce(anchor);
    whenShown(anchor, (el) => {
      // Smooth scrolling is compositor-driven, so it never progresses while the
      // document is hidden — a link opened in a background tab would land at the
      // top with nothing focused. Jump instantly in that case; animate when the
      // user is actually watching.
      const behavior: ScrollBehavior =
        document.visibilityState === "visible" ? "smooth" : "auto";
      el.scrollIntoView({ behavior, block: "center" });
      ring(el);
    });
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
  //    "Appears" means SHOWN: on a tabbed page the target can be mounted in a
  //    hidden panel (display:none) until the tab hook reads the hash, and a
  //    scroll to it would be a no-op that rang an invisible card.
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

    const cancel = whenShown(hash, (el) => {
      if (cancelled) return;
      // Instant, not smooth: a smooth scroll animates over the same window
      // in which `hold` is correcting position, and the two fight visibly.
      el.scrollIntoView({ behavior: "auto", block: "center" });
      ring(el);
      hold(el);
    });

    return () => {
      cancelled = true;
      cancel();
      observer?.disconnect();
      for (const id of timers) window.clearTimeout(id);
    };
  }, []);

  return focus;
}

export default useFocusSection;
