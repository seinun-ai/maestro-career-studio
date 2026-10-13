import type { ReactNode } from "react";

import { resumeColorStyle } from "@/lib/resume-color";
import { cn } from "@/lib/utils";

/** A base resume's colour as a 10px square. Identity, never state: its name always sits beside it
 *  (a `ResumeTag` is the pair), so it is hidden from assistive tech. Square and 2px-cornered on purpose: round
 *  means status in this app, and a faded fill means disabled. No hue draws neutral grey. */
export function ResumeSwatch({ hue, className }: { hue: number | null | undefined; className?: string }) {
  return (
    <span aria-hidden="true" style={resumeColorStyle(hue)}
      className={cn("size-2.5 shrink-0 rounded-corner-2xs bg-resume", className)} />
  );
}

/** The square, then the resume's name. Baseline-aligned: the square sits level with the name's first line, so a name that
 *  wraps keeps it there (the empty square's baseline is its bottom edge, about a capital's height). */
export function ResumeTag({ hue, children, className }: {
  hue: number | null | undefined; children: ReactNode; className?: string;
}) {
  return (
    <span className={cn("inline-flex items-baseline gap-1.5", className)}>
      <ResumeSwatch hue={hue} />
      {children}
    </span>
  );
}
