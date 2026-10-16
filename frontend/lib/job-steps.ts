/**
 * The job page's four steps as data: which one is current from the server's stage, and the one line under
 * each (the receipt under a done step, the hint under a future one). Pure, so `node --test` loads it; it
 * imports only types, which the loader erases (a value import would need a `.ts` path, which tsc rejects).
 */
import type { GapCounts } from "./gap-counts";
import type { Rung } from "./next-step";
import type { KnockoutStatus } from "./types";

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
  /** The knock-out scan; null = no scan. */
  knockout: { status: KnockoutStatus; notChecked: boolean } | null;
  base: { name: string | null; score: number | null };
  /** From lib/gap-counts; null = no gap analysis yet. */
  gaps: GapCounts | null;
  /** A draft exists when score is set. */
  draft: { score: number | null; changes: number | null };
  /** Null = no PDF (from the application's pdf_path, not the page count). createdOn is formatted by the caller. */
  pdf: { pages: number | null; createdOn: string | null } | null;
  /** lib/job-standing's text, for step 4. */
  standing: string;
};

const TITLES: Record<StepKey, string> = { job: "Job", fit: "Resume and gaps", output: "Tailored resume", qa: "Apply" };

/**
 * The knock-out card's words (lib/knockout-line `knockoutWords`, which reuses the card's own line). Copied,
 * not imported, so this file stays loadable by `node --test`; job-steps.test.ts pins the two equal.
 */
const KNOCKOUT_WORDS = {
  clear: "No knock-outs",
  conflict: "A knock-out",
  incomplete_profile: "An answer missing from your profile",
  unstated: "No requirements listed",
  notChecked: "Checks not run yet",
  none: "Requirements not checked",
} as const;

function knockoutWords(k: JobStepsInput["knockout"]): string {
  if (!k) return KNOCKOUT_WORDS.none;
  if (k.status === "unstated" && k.notChecked) return KNOCKOUT_WORDS.notChecked;
  return KNOCKOUT_WORDS[k.status];
}

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
  return join(skills, knockoutWords(i.knockout));
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

function outputSummary(i: JobStepsInput, state: StepState): string {
  const tailored = score(i.draft.score);
  if (state === "next") {
    // Back on gaps after tailoring: the draft is still there until the next tailor.
    return tailored ? join("Draft from before", tailored, "tailoring again replaces it") : "Review the changes, edit, Create PDF";
  }
  if (i.pdf) {
    const created = i.pdf.createdOn ? `PDF created ${i.pdf.createdOn}` : "PDF created";
    const pages = i.pdf.pages == null ? null : count(i.pdf.pages, "page", "pages");
    return join(tailored, pages ? `${created}, ${pages}` : created);
  }
  if (state === "current") {
    const c = i.draft.changes;
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
    const state: StepState = index < at ? "done" : index === at ? "current" : "next";
    const summary =
      key === "job" ? jobSummary(input)
      : key === "fit" ? fitSummary(input, state)
      : key === "output" ? outputSummary(input, state)
      : applySummary(input, state);
    return { key, number: (index + 1) as Step["number"], title: TITLES[key], state, summary };
  });
}
