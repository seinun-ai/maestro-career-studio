"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/** The AI is working: three dots that rise in turn beside what it is doing ("Writing your cover
 * letter"). It replaces a spinner where the work is shown; the dots are decoration. With reduced
 * motion the dots hold still (globals.css).
 *
 * SPOKEN RELIABLY however it is mounted. A `role="status"` region that appears with its words already
 * inside is often not announced: screen readers speak a live region's CHANGES, and need the region in
 * the page first. Callers mount this while the work runs (`{pending ? <WorkingDots …/> : null}`), so
 * the region mounts empty and its words are written a moment later (`SPEAK_AFTER_MS`; the region has
 * no React children, so the write is its own); the words show at once for the eye (`aria-hidden`),
 * and a new `label` is spoken as it changes. */
// Long enough that the region is in the page, and painted, before its words arrive: an effect alone can
// run in the same task as the mount (React flushes a click's effects at once).
const SPEAK_AFTER_MS = 100;

export function WorkingDots({ label, className }: { label: string; className?: string }) {
  const region = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = region.current;
    if (!node) return;
    const timer = window.setTimeout(() => {
      node.textContent = label;
    }, SPEAK_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [label]);
  return (
    <span className={cn("inline-flex items-center gap-3 text-label-large", className)}>
      <span aria-hidden="true" className="inline-flex h-5 items-center gap-1">
        <span className="working-dot" />
        <span className="working-dot" />
        <span className="working-dot" />
      </span>
      <span aria-hidden="true">{label}</span>
      <span ref={region} role="status" className="sr-only" />
    </span>
  );
}
