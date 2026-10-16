/**
 * The job page's four steps as data: which one is current from the server's stage, and the one line under
 * each (the receipt under a done step, the hint under a future one). Pure, so `node --test` loads it; it
 * imports only types, which the loader erases (a value import would need a `.ts` path, which tsc rejects).
 */
import type { GapCounts } from "./gap-counts";
import type { Rung } from "./next-step";

/** The tab values, kept so old deep links (`?tab=`) still land on a step. */
export type StepKey = "job" | "fit" | "output" | "qa";
export const STEP_KEYS: readonly StepKey[] = ["job", "fit", "output", "qa"];

/** ?tab= values the app has always written, mapped to a step; unknown → "job". */
export const TAB_TO_STEP: Readonly<Record<string, StepKey>> = {
  jd: "job", fit: "fit", output: "output", qa: "qa", submitted: "qa",
};

export function stepForTab(tab: string | null | undefined): StepKey {
  return (tab != null && Object.hasOwn(TAB_TO_STEP, tab) && TAB_TO_STEP[tab]) || "job";
}

/**
 * `done` may follow `current`: a later step whose result already exists (a draft from before a re-analysis
 * of the gaps) is done, so it stays reachable. Only a later step with nothing to show is `next`.
 */
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
  skills: { total: number; required: number };
  /** The knock-out card's words (lib/knockout-line `knockoutWords`, computed by the page); null = say nothing. */
  knockout: string | null;
  base: { name: string | null; score: number | null };
  /** From lib/gap-counts; null = no gap analysis yet. */
  gaps: GapCounts | null;
  /** Null = no draft (the application's customized_json is absent). */
  draft: { score: number | null; changes: number | null } | null;
  /** Null = no PDF (from the application's pdf_path, not the page count). createdOn is formatted by the caller. */
  pdf: { pages: number | null; createdOn: string | null } | null;
  /** lib/job-standing's text, for step 4. */
  standing: string;
};

const TITLES: Record<StepKey, string> = { job: "Job", fit: "Resume and gaps", output: "Tailored resume", qa: "Apply" };

/** The parts that are set, joined, the first letter capitalised. */
function join(...parts: (string | null)[]): string {
  const line = parts.filter((p): p is string => !!p).join(" · ");
  return line.charAt(0).toUpperCase() + line.slice(1);
}
const score = (n: number | null) => (n == null ? null : `${n.toFixed(1)} / 100`);
const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function jobSummary(i: JobStepsInput): string {
  const skills = i.skills.total > 0
    ? `${count(i.skills.total, "skill", "skills")}, ${i.skills.required} required`
    : "No skills found";
  return join(skills, i.knockout);
}

/** Step 2 is current or done: "next" never reaches here, as currentStep never returns "job". */
function fitSummary(i: JobStepsInput, state: StepState): string {
  const { name } = i.base;
  const g = i.gaps;
  if (state === "done") {
    const gaps = !g ? null
      : g.total === 0 ? "no gaps found"
      : `${count(g.answered, "gap", "gaps")} answered, ${g.skipped} skipped`;
    return join(name, score(i.base.score), gaps) || "No gaps analyzed";
  }
  if (!g) return "Pick a resume and analyze its gaps";
  if (g.total === 0) return join(name, "no gaps found");
  // Resolved is answered or skipped, as the server's stage counts gaps_done.
  return join(name, `${g.answered + g.skipped} of ${count(g.total, "gap", "gaps")} closed`);
}

/** Step 3 has a result to show: a draft, or a PDF made from one. */
const hasOutput = (i: JobStepsInput) => i.draft != null || i.pdf != null;

function outputSummary(i: JobStepsInput, state: StepState, ahead: boolean): string {
  const tailored = score(i.draft?.score ?? null);
  if (state === "next") return "Review the changes, edit, Create PDF";
  if (ahead) {
    // Back on gaps after tailoring: the draft is still there until the next tailor.
    return join(tailored ? `Draft from before, ${tailored}` : "Draft from before", "Tailor again to replace it");
  }
  if (i.pdf) {
    const created = i.pdf.createdOn ? `PDF created ${i.pdf.createdOn}` : "PDF created";
    const pages = i.pdf.pages == null ? null : count(i.pdf.pages, "page", "pages");
    return join(tailored, pages ? `${created}, ${pages}` : created);
  }
  if (state === "current") {
    const c = i.draft?.changes ?? null;
    const changes = c == null ? null : c === 0 ? "no changes to review" : `${count(c, "change", "changes")} to review`;
    return join(changes, tailored, "no PDF yet");
  }
  // Done without a PDF: the job went on to Apply without one (marked applied by hand, or closed).
  return join(tailored, "no PDF");
}

function applySummary(i: JobStepsInput, state: StepState): string {
  if (state === "current") return i.standing;
  return i.pdf ? "Questions, cover letter, Mark applied" : "After Create PDF";
}

export function jobSteps(input: JobStepsInput): Step[] {
  const at = STEP_KEYS.indexOf(currentStep(input.stage));
  return STEP_KEYS.map((key, index) => {
    const ahead = index > at;
    // A later step with a result keeps it reachable (only step 3 can: step 4's result is the stage itself).
    const state: StepState = index < at ? "done" : index === at ? "current" : key === "output" && hasOutput(input) ? "done" : "next";
    const summary =
      key === "job" ? jobSummary(input)
      : key === "fit" ? fitSummary(input, state)
      : key === "output" ? outputSummary(input, state, ahead)
      : applySummary(input, state);
    return { key, number: (index + 1) as Step["number"], title: TITLES[key], state, summary };
  });
}
