"use client";

import { useState, type ReactNode } from "react";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ResumeSwatch } from "@/components/visual";
import { cn } from "@/lib/utils";

/** How many chips show before "N more": the design's top 3 by score. */
const CHIPS_SHOWN = 3;

/** One chip: a base resume, its colour, its Match score. */
export type ResumeChipOption = {
  slug: string;
  name: string;
  score: number;
  hue: number | null | undefined;
};

/**
 * The base resumes as a row of chips, one picked: step 2 of the job page, and the gap page (Task 11). A pick is a
 * preview: it changes what the step shows and never writes, so each chip is a toggle button (FilterChips'
 * semantics: `aria-pressed`, 28px, a leading Check and `secondary-container` when on), one on at a time. Sorted
 * by score; the top 3 show, then "N more" reveals the rest, and the picked chip always shows. While `busy`, a chip
 * stays focusable (`aria-disabled`) and a press does nothing. `actions` sits at the row's right end (step 2's ⋯).
 */
export function ResumeChips({
  resumes,
  picked,
  onPick,
  best,
  busy = false,
  actions,
}: {
  resumes: readonly ResumeChipOption[];
  picked: string | null;
  onPick: (slug: string) => void;
  /** The best match's slug: its chip wears Best. */
  best: string | null;
  busy?: boolean;
  actions?: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const sorted = [...resumes].sort((a, b) => b.score - a.score);
  const shown = expanded
    ? sorted
    : sorted.filter((r, i) => i < CHIPS_SHOWN || r.slug === picked);
  const hidden = sorted.length - shown.length;
  return (
    <div className="flex items-start gap-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <div role="group" aria-label="Base resume" className="flex min-w-0 flex-wrap items-center gap-2">
          {shown.map((r) => {
            const on = r.slug === picked;
            const isBest = r.slug === best;
            const score = r.score.toFixed(1);
            return (
              <button
                key={r.slug}
                type="button"
                title={r.name}
                aria-pressed={on}
                aria-disabled={busy || undefined}
                aria-label={`${r.name}, Match score ${score}${isBest ? ", best" : ""}`}
                onClick={() => {
                  if (!busy && !on) onPick(r.slug);
                }}
                className={cn(
                  "inline-flex h-7 min-w-0 cursor-pointer items-center gap-1.5 rounded-full border px-3 text-label-medium whitespace-nowrap transition-colors duration-(--duration-short3) ease-(--ease-standard) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:cursor-default aria-disabled:opacity-50",
                  on
                    ? "border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
                    : "border-border hover:bg-surface-container",
                )}
              >
                {on && <Check className="size-3 shrink-0" aria-hidden="true" />}
                <ResumeSwatch hue={r.hue} />
                <span className="max-w-48 min-w-0 truncate">{r.name}</span>
                <span className="tabular-nums">{score}</span>
                {isBest && <Badge variant="secondary">Best</Badge>}
              </button>
            );
          })}
        </div>
        {hidden > 0 || expanded ? (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-7 px-1"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Show fewer" : `${hidden} more`}
          </Button>
        ) : null}
      </div>
      {actions}
    </div>
  );
}
