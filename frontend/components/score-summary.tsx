"use client";

import { useState } from "react";

import { AnchorPills } from "@/components/base-resumes/anchor-pills";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { ResumeTag, ScoreBar } from "@/components/visual";
import { useCountUp } from "@/hooks/use-count-up";
import { SUBSCORE_LABELS, UNREADABLE_DATES_NOTE, datesUnreadable } from "@/lib/ats-words";
import type { AtsScore, BaseResumeSummary } from "@/lib/types";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const WarningIcon = CONCEPT_ICONS.warning;

/** The server's low-coverage sentence, on the row or (older rows) inside its subscores. */
export function coverageWarning(score: AtsScore): string | null {
  return score.coverage_warning || score.subscores_json?.coverage_warning || null;
}

/** One subscore as a meter out of 100: the number sits beside the bar, so no " of 100" is needed. */
export function SubscoreBar({ label, value, weakest }: { label: string; value: number; weakest: boolean }) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="text-muted-foreground text-body-small">{label}</span>
        {/* A word only (D4): no colour, no threshold; the arrow icon means Lost elsewhere. */}
        {weakest && (
          <span className="inline-flex h-4 items-center rounded-full bg-surface-container px-1.5 text-label-small">Weakest</span>
        )}
      </div>
      <ScoreBar value={Math.round(value * 100)} max={100} label={label} width="flex-1" className="w-full" />
    </div>
  );
}

/** The index of the lowest value (ties go to the first); -1 when all are equal, since none is weakest. */
export function lowestIndex(values: number[]): number {
  if (Math.max(...values) === Math.min(...values)) return -1;
  return values.reduce((low, v, i) => (v < values[low] ? i : low), 0);
}

/**
 * The picked resume's score in one line, with the breakdown behind a popover: the subscores, the skills
 * covered, its Target pills, the dates note and its own warnings (shared ones sit above the chips). Step 2 of
 * the job page draws it under the resume chips.
 */
export function ScoreSummary({
  score,
  resume,
  name,
  showCoverage,
  sharedWarnings,
}: {
  score: AtsScore;
  resume: BaseResumeSummary | undefined;
  name: string;
  /** False when the banner already says every resume shows too few of the job's skills. */
  showCoverage: boolean;
  /** Gate warnings every resume carries: the banner says them once, so the popover leaves them out. */
  sharedWarnings: Set<string>;
}) {
  // Open for one resume: a new pick closes it, while the score below counts from the last one to this one.
  const [openFor, setOpenFor] = useState<string | null>(null);
  const open = openFor === score.target_id;
  const setOpen = (next: boolean) => setOpenFor(next ? score.target_id : null);
  const shownScore = useCountUp(score.composite);
  const subscoreValues = SUBSCORE_LABELS.map(({ key }) => score.subscores_json[key] ?? 0);
  const weakestAt = lowestIndex(subscoreValues);
  const extracted = score.jd_skills_extracted_count ?? 0;
  const matched = score.jd_skills_matched_count ?? 0;
  const gateWarnings = (score.subscores_json.gate_warnings ?? []).filter((w) => !sharedWarnings.has(w));
  const coverage = showCoverage ? coverageWarning(score) : null;
  return (
    <div className="bg-surface-container-low flex flex-wrap items-center gap-x-6 gap-y-1 rounded-corner-md px-4 py-2">
      <div className="text-headline-small tabular-nums">
        {shownScore.toFixed(1)}
        <span className="text-muted-foreground text-body-medium"> / 100</span>
      </div>
      {extracted > 0 && (
        <p className="text-body-medium">
          <span className="text-muted-foreground">Skills covered</span>{" "}
          <span className="tabular-nums">{matched} of {extracted}</span>
        </p>
      )}
      {weakestAt >= 0 && (
        <p className="text-body-medium">
          <span className="text-muted-foreground">Weakest</span> {SUBSCORE_LABELS[weakestAt].label}
        </p>
      )}
      {/* The details of one resume's score, anchored to its button: a panel, not a dialog. */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <Button type="button" variant="link" size="sm" className="ml-auto h-auto px-0" aria-expanded={open}>
              Score breakdown
            </Button>
          }
        />
        <PopoverContent align="end" className="w-80 space-y-3">
          <div className="grid gap-1">
            <PopoverTitle>
              <ResumeTag hue={resume?.color_hue} className="max-w-full">
                <span className="min-w-0 truncate" title={name}>{name}</span>
              </ResumeTag>
            </PopoverTitle>
            {resume && <AnchorPills resume={resume} />}
          </div>
          <div className="grid gap-y-1.5">
            {SUBSCORE_LABELS.map(({ key, label }, i) => (
              <SubscoreBar key={key} label={label} value={subscoreValues[i]} weakest={i === weakestAt} />
            ))}
          </div>
          {extracted > 0 && (
            <div className="space-y-0.5">
              <span className="text-muted-foreground text-body-small">Skills covered</span>
              <ScoreBar
                value={matched}
                max={extracted}
                label="Skills covered"
                valueText={`${matched} of ${extracted}`}
                width="flex-1"
                className="w-full"
              />
            </div>
          )}
          {datesUnreadable(score.subscores_json.format_flags) && (
            <p className="text-muted-foreground text-body-small">{UNREADABLE_DATES_NOTE}</p>
          )}
          {(gateWarnings.length > 0 || coverage) && (
            <ul className="space-y-1 text-body-small">
              {gateWarnings.map((warning) => (
                <li key={warning} className="text-warning flex gap-1.5">
                  <WarningIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
                  {warning}
                </li>
              ))}
              {coverage && (
                <li className="text-warning flex gap-1.5">
                  <WarningIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
                  {/* The server's sentence already gives the counts ("Your resume shows only 1 of this job's 8 skills (13%)."). */}
                  {coverage}
                </li>
              )}
            </ul>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
