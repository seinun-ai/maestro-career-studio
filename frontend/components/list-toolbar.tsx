"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The `tall:` variant's query (app/globals.css). Below it nothing sticks. */
export const TALL_QUERY = "(min-height: 40rem)";
/** Read by a sticky TableHeader's `top` and by html's scroll-padding-top. */
const STICKY_TOP_VAR = "--list-sticky-top";

/**
 * The search, filter and sort controls above a long list. The toolbar sticks
 * to the top of the window while the list scrolls under it, and a sticky
 * table header (`<Table stickyHeader>`) sticks right under it.
 *
 * The header cannot know the toolbar's height (it wraps at narrow widths, and
 * a filter label carries a count), so the toolbar measures itself and
 * publishes the height as `--list-sticky-top` on <html>. It goes on <html>
 * and not on a wrapper because html's `scroll-padding-top` reads it too:
 * that is what keeps a focused row from landing under the stuck chrome
 * (WCAG 2.4.11, technique C43).
 *
 * A `<search>` landmark: HTML's element for search and filtering controls.
 * Not `role="toolbar"`, which promises arrow-key roving between controls;
 * these are separate Tab stops.
 *
 * One per page. Nothing sticks below `TALL_QUERY`: on a landscape phone or at
 * high zoom, the stuck chrome would take too much of the screen (WCAG 1.4.10).
 */
export function ListToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement;
    const tall = window.matchMedia(TALL_QUERY);
    let written = "";
    const write = () => {
      // floor, not ceil: a header placed a fraction of a pixel too HIGH
      // tucks under the toolbar (z-30 over z-10); too LOW leaves a slit
      // that rows show through.
      written = tall.matches
        ? `${Math.floor(el.getBoundingClientRect().height)}px`
        : "0px";
      root.style.setProperty(STICKY_TOP_VAR, written);
    };
    write();
    const observer = new ResizeObserver(write);
    observer.observe(el);
    tall.addEventListener("change", write);
    return () => {
      observer.disconnect();
      tall.removeEventListener("change", write);
      // Only our own value: a list page that mounted before this one
      // unmounted has written its own.
      if (root.style.getPropertyValue(STICKY_TOP_VAR) === written) root.style.removeProperty(STICKY_TOP_VAR);
    };
  }, []);
  return (
    <search
      ref={ref}
      data-slot="list-toolbar"
      className={cn(
        // -my-3 py-3: the same place in the flow, with 12px of page colour
        // above and below the controls once stuck. z-30: over a gallery
        // card's z-20 actions, under the fixed bulk bar (z-40) and every
        // portalled popup (z-50).
        "bg-background -my-3 flex flex-col gap-3 py-3 tall:sticky tall:top-0 tall:z-30 print:static",
        className,
      )}
    >
      {children}
    </search>
  );
}
