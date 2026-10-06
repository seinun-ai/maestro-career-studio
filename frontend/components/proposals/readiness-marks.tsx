import { CircleCheck, TriangleAlert } from "lucide-react";

import { DotMeter } from "@/components/visual";
import { isReady, readinessMarks, readinessSteps, type Readiness } from "@/lib/inbox-readiness";

/**
 * A row's readiness: ready is quiet (a neutral chip, the check in the success colour), otherwise a meter of the
 * three steps. A knock-out or answers to check stay loud as warning chips. Nothing when unknown.
 */
export function ReadinessMarks({ readiness }: { readiness: Readiness | null | undefined }) {
  const steps = readinessSteps(readiness);
  if (!steps) return null;
  const warnings = readinessMarks(readiness).filter((mark) => mark.tone === "warning");
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {isReady(readiness) ? (
        <span className="inline-flex h-5 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground">
          <CircleCheck className="size-3 shrink-0 text-success" aria-hidden="true" />
          Ready
        </span>
      ) : (
        <DotMeter name="Ready" filled={steps.done} total={steps.total} word={`${steps.done} of ${steps.total} ready`} className="text-muted-foreground" />
      )}
      {warnings.map((mark) => (
        <span key={mark.text} className="inline-flex items-center gap-1 rounded-full bg-warning-container px-2 py-0.5 text-label-small text-on-warning-container">
          <TriangleAlert className="size-3 shrink-0" aria-hidden="true" />
          {mark.text}
        </span>
      ))}
    </span>
  );
}
