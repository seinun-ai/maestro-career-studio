"use client";

import type { ReactNode } from "react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { GRADE_STYLES } from "@/components/resume-health/finding-cards";
import type { ScoreDelta } from "@/components/resume-health/use-health-runs";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  nextGradeLine,
  nextGradeProgress,
  reportInsufficientEvidence,
  scoreCompositionLine,
} from "@/lib/health-report";
import { cn } from "@/lib/utils";
import type { LintFinding, LintReport } from "@/lib/types";

// The career stage the score is judged against (`health_zones.compute_tier`).
// "unknown" (no dates to read) shows no badge: it is not a stage.
const TIER_LABELS: Record<string, string | undefined> = {
  early: "Early career",
  experienced: "Experienced",
};

/**
 * The report's full-width summary: the grade, the bar to the next band, what capped the score, what
 * is left and what the user marked not right, the page's ONE filled control (Start the questions),
 * the "No numbers anywhere" callout, and `children` (the stale banner).
 */
export function SummaryBand({
  body,
  scoreDelta,
  remaining,
  marked,
  askCount,
  startHref,
  noNumbers,
  numberCount,
  onOpenNumberTab,
  children,
}: {
  body: LintReport;
  scoreDelta: ScoreDelta | null;
  remaining: number;
  /** Disputes on file ("Not right?"). */
  marked: number;
  askCount: number;
  /** The question pass, carrying the tab to come back to. */
  startHref: string;
  noNumbers: LintFinding | null;
  numberCount: number;
  onOpenNumberTab: () => void;
  children?: ReactNode;
}) {
  const insufficient = reportInsufficientEvidence(body);
  const gates = body.gates ?? [];
  const composition = scoreCompositionLine(body.score, body.score_breakdown, gates);
  const progress = !insufficient ? nextGradeProgress(body) : null;
  return (
    <section
      data-summary-band
      aria-label="Summary"
      className="flex min-w-0 flex-col gap-3 rounded-corner-md border p-4"
    >
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <div className="flex items-center gap-3">
          {insufficient ? (
            <span className="text-muted-foreground flex size-14 items-center justify-center rounded-corner-sm text-center text-label-small">
              Too little to grade
            </span>
          ) : (
            <span
              className={cn(
                "flex size-14 items-center justify-center rounded-corner-sm text-headline-small font-semibold",
                GRADE_STYLES[body.grade] ?? GRADE_STYLES.C,
              )}
            >
              {body.grade}
            </span>
          )}
          <div className="flex min-w-0 flex-col gap-1">
            <span className={cn("text-title-small", insufficient && "text-muted-foreground")}>
              {body.score}/100
            </span>
            {scoreDelta && (
              <div className="space-y-0.5">
                <p className="text-body-small">
                  {scoreDelta.fromGrade} {scoreDelta.fromScore} →{" "}
                  {scoreDelta.toGrade} {scoreDelta.toScore}
                  {scoreDelta.toScore - scoreDelta.fromScore !== 0 && (
                    <span className="text-muted-foreground">
                      {", "}
                      {scoreDelta.toScore - scoreDelta.fromScore > 0 ? "+" : ""}
                      {scoreDelta.toScore - scoreDelta.fromScore}
                    </span>
                  )}
                </p>
                {scoreDelta.explanation && (
                  <p className="text-muted-foreground max-w-[40ch] text-body-small">
                    {scoreDelta.explanation}
                  </p>
                )}
              </div>
            )}
            {body.tier && TIER_LABELS[body.tier] && (
              <Badge variant="secondary" className="w-fit">
                {TIER_LABELS[body.tier]}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex min-w-48 flex-1 basis-56 flex-col gap-1.5">
          {/* The bar is decoration: the line under it says the same in words. */}
          {progress != null && (
            <div aria-hidden className="bg-muted h-1.5 w-full max-w-sm overflow-hidden rounded-full">
              <div
                className="bg-primary h-full rounded-full"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          )}
          {!insufficient && nextGradeLine(body) && (
            <p className="text-muted-foreground text-body-small">{nextGradeLine(body)}</p>
          )}
          {composition && <p className="text-muted-foreground text-body-small">{composition}</p>}
          <p className="text-muted-foreground text-body-small">
            {remaining} left to fix
            {marked > 0 && <> · {marked} marked not right</>}
          </p>
        </div>
        {/* A link styled as the filled button, not a Button rendering a link (SYSTEM.md §11 item 29:
            that announces a link as a button). */}
        {askCount > 0 && (
          <Link href={startHref} className={cn(buttonVariants(), "ml-auto")}>
            Start the questions ({askCount})
          </Link>
        )}
      </div>

      {noNumbers && (
        <div
          role="note"
          className="rounded-corner-md bg-warning-container px-3 py-2 text-body-medium text-on-warning-container"
        >
          <p className="font-medium">{noNumbers.label}</p>
          <p className="mt-0.5 max-w-[65ch]">
            {noNumbers.issue} {noNumbers.why}
          </p>
          <p className="mt-0.5 max-w-[65ch]">{noNumbers.how}</p>
          {numberCount > 0 && (
            <Button size="xs" variant="link" className="mt-1 h-auto px-0" onClick={onOpenNumberTab}>
              Go to Needs a number ({numberCount})
            </Button>
          )}
        </div>
      )}

      {children}
    </section>
  );
}
