"use client";

import { SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * The one control a list's rarer filters sit behind. It opens a row of them in place (`controls` is that
 * row's id, which the caller hides while closed), and says how many of them are on, so a filter set from a
 * link or an earlier visit is never hidden without a word.
 */
export function FiltersButton({
  open,
  onToggle,
  controls,
  active,
}: {
  open: boolean;
  onToggle: () => void;
  controls: string;
  /** How many of the filters behind it are on. */
  active: number;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="shrink-0 tabular-nums"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
    >
      <SlidersHorizontal aria-hidden="true" />
      {active > 0 ? `Filters · ${active}` : "Filters"}
    </Button>
  );
}
