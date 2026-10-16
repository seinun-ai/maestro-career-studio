/**
 * The Jobs list's Next step: the one control a row shows, from the stage the server computes
 * (backend/app/services/stage.py). No imports: `node --test` loads this file as it is.
 */

/** The server's rungs. `closed` is rejected or withdrawn and `applied` every submitted status: neither ranks by position. */
export type Rung = "saved" | "scored" | "gaps" | "tailored" | "pdf_ready" | "applied" | "closed";

export type NextStep = {
  label: string;
  variant: "ghost" | "tonal" | "default";
  tab: "fit" | "output" | "qa";
  session?: string | null;
} | null;

/**
 * The one control a row shows. Null once applied or closed: the status chip carries the job from there.
 * Null too when the stage is missing (a backend that predates it), so such a row shows nothing.
 */
export function nextStep(
  stage: Rung | null | undefined,
  s: { open_session_id?: string | null; gaps_done?: number; gaps_total?: number },
): NextStep {
  switch (stage) {
    case "saved":
      return { label: "Score", variant: "ghost", tab: "fit" };
    case "scored":
      return { label: "Analyze gaps", variant: "ghost", tab: "fit" };
    case "gaps":
      return {
        label: `Continue gaps · ${s.gaps_done ?? 0} of ${s.gaps_total ?? 0}`,
        variant: "tonal",
        tab: "fit",
        session: s.open_session_id,
      };
    case "tailored":
      return { label: "Review resume", variant: "tonal", tab: "output" };
    case "pdf_ready":
      return { label: "Apply", variant: "default", tab: "qa" };
    default:
      return null;
  }
}

/** Where a step's control goes: the open gap analysis itself, else the job page on the step's tab. */
export function nextStepHref(jobId: string, step: NonNullable<NextStep>): string {
  return step.session ? `/jobs/${jobId}/tailor/${step.session}` : `/jobs/${jobId}?tab=${step.tab}`;
}
