"use client";

import { ViewTransition, type ReactElement } from "react";

import { morphName } from "@/lib/view-transition";

/**
 * The company's monogram or the job's title, on a Jobs row and in the job page's header: the one pair that morphs
 * when a row opens its job, and back by Back to Jobs or the browser's Back (design refresh Task 4.5; globals.css
 * `.job-morph`, 250ms; the way back is lib/view-transition.ts and the leave guard's `holdForMorph`). `default="none"`
 * keeps every other transition from animating it, and `share` is what pairs it (with `default="none"` and no
 * `share`, the pair silently stops morphing). `off` draws the child without a name: a row opened from the keyboard
 * opens without the morph, since keyboard actions do not animate.
 */
export function JobMorph({
  jobId,
  part,
  off = false,
  children,
}: {
  jobId: string;
  part: "monogram" | "title";
  off?: boolean;
  /** One element: the name goes on its DOM node. */
  children: ReactElement;
}) {
  if (off) return children;
  return (
    <ViewTransition name={morphName(jobId, part)} share="job-morph" default="none">
      {children}
    </ViewTransition>
  );
}
