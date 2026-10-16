/**
 * The job page's four steps as data: which one is current from the server's stage, and the one line under
 * each (the receipt under a done step, the hint under a future one). Pure, so `node --test` loads it; the
 * only import is a type, which the loader erases.
 */
import type { Rung } from "./next-step";

/** The tab values, kept so old deep links (`?tab=`) still land on a step. */
export type StepKey = "job" | "fit" | "output" | "qa";
export const STEP_KEYS: readonly StepKey[] = ["job", "fit", "output", "qa"];

/** ?tab= values the app has always written, mapped to a step; unknown → "job". */
export const TAB_TO_STEP: Record<string, StepKey> = { jd: "job", fit: "fit", output: "output", qa: "qa", submitted: "qa" };

export function stepForTab(tab: string | null | undefined): StepKey {
  return (tab != null && Object.hasOwn(TAB_TO_STEP, tab) && TAB_TO_STEP[tab]) || "job";
}

export type StepState = "done" | "current" | "next";
export type Step = { key: StepKey; number: 1 | 2 | 3 | 4; title: string; state: StepState; summary: string };

/**
 * The current step from the stage: saved/scored/gaps → fit; tailored/pdf_ready → output; applied/closed → qa.
 * Never "job": the job exists once saved, so step 1 is always done and step 2 is never next. A rung that
 * would make the job step current is a deliberate change here, and needs a "next" wording for step 2.
 */
export function currentStep(stage: Rung): Exclude<StepKey, "job"> {
  switch (stage) {
    case "tailored":
    case "pdf_ready":
      return "output";
    case "applied":
    case "closed":
      return "qa";
    default:
      return "fit";
  }
}

export type JobStepsInput = {
  stage: Rung;
  skillsTotal: number;
  requiredTotal: number;
  /** The knock-out scan's overall verdict; null = not run. */
  knockout: "clear" | "conflict" | "unstated" | null;
  resumeName: string | null;
  baseScore: number | null;
  gapsDone: number;
  gapsSkipped: number;
  gapsTotal: number;
  tailoredScore: number | null;
  changes: number | null;
  pdfPages: number | null;
  /** Already formatted by the caller. */
  pdfCreatedOn: string | null;
  /** lib/job-standing's text, for step 4. */
  standing: string;
};

const TITLES: Record<StepKey, string> = { job: "Job", fit: "Resume and gaps", output: "Tailored resume", qa: "Apply" };

const KNOCKOUT: Record<"clear" | "conflict" | "unstated" | "none", string> = {
  clear: "no knock-outs",
  conflict: "a knock-out: see the job",
  unstated: "requirements not stated",
  none: "requirements not checked",
};

const join = (...parts: (string | null)[]) => parts.filter((p): p is string => !!p).join(" · ");
const score = (n: number | null) => (n == null ? null : n.toFixed(1));
const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function jobSummary(i: JobStepsInput): string {
  const skills = i.skillsTotal > 0
    ? `${count(i.skillsTotal, "skill", "skills")}, ${i.requiredTotal} required`
    : "No skills found";
  return join(skills, KNOCKOUT[i.knockout ?? "none"]);
}

/** Step 2 is current or done, never next (see currentStep). */
function fitSummary(i: JobStepsInput, state: Exclude<StepState, "next">): string {
  if (state === "current") {
    return i.gapsTotal > 0
      ? join(i.resumeName, `${i.gapsDone} of ${i.gapsTotal} gaps closed`)
      : "Pick a resume and analyze its gaps";
  }
  const gaps = i.gapsTotal > 0 ? `${i.gapsDone} gaps closed, ${i.gapsSkipped} skipped` : null;
  return join(i.resumeName, score(i.baseScore), gaps) || "No gaps analyzed";
}

function outputSummary(i: JobStepsInput, state: StepState): string {
  if (state === "next") return "Review the changes, edit, Create PDF";
  if (i.pdfPages != null) {
    const created = i.pdfCreatedOn ? `PDF created ${i.pdfCreatedOn}` : "PDF created";
    return join(score(i.tailoredScore), `${created}, ${count(i.pdfPages, "page", "pages")}`);
  }
  if (state === "current") {
    const changes = i.changes == null ? null : `${count(i.changes, "change", "changes")} to review`;
    return join(changes, score(i.tailoredScore), "no PDF yet");
  }
  // Done without a PDF: the job went on to Apply without one (marked applied by hand, or closed).
  const tailored = score(i.tailoredScore);
  return tailored ? `${tailored} · no PDF` : "No PDF";
}

function applySummary(i: JobStepsInput, state: StepState): string {
  if (state === "current") return i.standing;
  const pdfMade = i.stage === "pdf_ready" || i.pdfPages != null;
  return pdfMade ? "Questions, cover letter, Mark applied" : "After Create PDF";
}

export function jobSteps(input: JobStepsInput): Step[] {
  const at = STEP_KEYS.indexOf(currentStep(input.stage));
  return STEP_KEYS.map((key, index) => {
    const state: StepState = index < at ? "done" : index === at ? "current" : "next";
    const summary =
      key === "job" ? jobSummary(input)
      : key === "fit" ? fitSummary(input, state === "done" ? "done" : "current")
      : key === "output" ? outputSummary(input, state)
      : applySummary(input, state);
    return { key, number: (index + 1) as Step["number"], title: TITLES[key], state, summary };
  });
}
