import { DotMeter } from "@/components/visual";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { isReady, readinessMarks, readinessSteps, type Readiness } from "@/lib/inbox-readiness";

/**
 * A row's readiness: ready is quiet (a neutral chip, the check in the success colour), otherwise a meter of the
 * three steps. A knock-out is a conflict (error chip, as on the job Overview); answers to check stay warning chips. Nothing when unknown.
 */
export function ReadinessMarks({ readiness }: { readiness: Readiness | null | undefined }) {
  const steps = readinessSteps(readiness);
  if (!steps) return null;
  const marks = readinessMarks(readiness);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {isReady(readiness) ? (
        <span className="inline-flex h-5 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground">
          <CONCEPT_ICONS.done className="size-3 shrink-0 text-success" aria-hidden="true" />
          Ready
        </span>
      ) : (
        <DotMeter name="Ready" filled={steps.done} total={steps.total} word={`${steps.done} of ${steps.total} ready`} label={`${steps.done} of ${steps.total} ready`} className="text-muted-foreground" />
      )}
      {/* Which step the meter is missing; unknown (null) counts as not done but claims nothing. */}
      {readiness?.tailored === false ? <span className="text-muted-foreground text-label-small">Not tailored</span> : null}
      {marks.map((mark) => {
        const Icon = mark.tone === "error" ? CONCEPT_ICONS.fails : CONCEPT_ICONS.warning;
        const tone = mark.tone === "error" ? "bg-error-container text-on-error-container" : "bg-warning-container text-on-warning-container";
        return (
          <span key={mark.text} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-label-small ${tone}`}>
            <Icon className="size-3 shrink-0" aria-hidden="true" />
            {mark.text}
          </span>
        );
      })}
    </span>
  );
}
