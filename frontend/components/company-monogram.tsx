"use client";

import { cn } from "@/lib/utils";

/** A company's initial on a neutral disc. Neutral on purpose: the base resume
 *  square is the only hue in a row, and StatusChip is the only place a state
 *  is coloured, so the name picks no tone. The fill is the ladder's highest
 *  step so it stays visible on a hovered row (dark rows hover to -high), and
 *  `foreground` holds AA on it in both modes (test_frontend_design_tokens.py).
 *  Decoration: the name beside it carries the meaning. */
export function CompanyMonogram({
  name,
  className,
}: {
  name: string | null | undefined;
  className?: string;
}) {
  const label = (name ?? "").trim();
  const initial = label ? label[0].toUpperCase() : "?";
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-container-highest text-label-large text-foreground",
        className,
      )}
    >
      {initial}
    </span>
  );
}
