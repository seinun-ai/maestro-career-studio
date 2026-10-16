/**
 * The job page's four steps as data: which one is current from the server's stage, and the one line under
 * each (the receipt under a done step, the hint under a future one). Pure, so `node --test` loads it; it
 * imports only types, which the loader erases (a value import would need a `.ts` path, which tsc rejects).
 */
import type { GapCounts } from "./gap-counts";
import type { Rung } from "./next-step";
import type { Application, Job, TailoringSession } from "./types";

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

/** Where the stage is: before it, at it, after it. A step after it is `next` even when it has something to show. */
export type StepState = "done" | "current" | "next";
/**
 * `reachable`: the step has a panel worth opening. Steps 1 and 2 always; step 3 once there is a draft or a
 * PDF (a draft from before a re-analysis included); step 4 once the job has an application. A `next` step
 * that is reachable is still a button: nothing with content is locked, and nothing is ticked that is not done.
 */
export type Step = {
  key: StepKey;
  number: 1 | 2 | 3 | 4;
  title: string;
  state: StepState;
  reachable: boolean;
  summary: string;
};

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
  /** The open gap analysis's count while step 2 is current (the server's: closed = answered or skipped); null = none. */
  openGaps: { closed: number; total: number } | null;
  /** The gaps of the analysis that made the draft, for a done step 2 (lib/gap-counts); null = none. */
  draftGaps: GapCounts | null;
  /** Null = no draft (the application's customized_json is absent). */
  draft: { score: number | null; changes: number | null } | null;
  /** Null = no PDF (from the application's pdf_path, not the page count). createdOn is formatted by the caller. */
  pdf: { pages: number | null; createdOn: string | null } | null;
  /** lib/job-standing's text, for step 4. */
  standing: string;
  /** The job has an application: step 4 has a panel. */
  hasApplication: boolean;
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
  if (state === "done") {
    const g = i.draftGaps;
    const gaps = !g ? null
      : g.total === 0 ? "no gaps found"
      : `${count(g.answered, "gap", "gaps")} answered, ${g.skipped} skipped`;
    return join(name, score(i.base.score), gaps) || "No gaps analyzed";
  }
  const g = i.openGaps;
  if (!g) return "Pick a resume and analyze its gaps";
  if (g.total === 0) return join(name, "no gaps found");
  return join(name, `${g.closed} of ${count(g.total, "gap", "gaps")} closed`);
}

/** Step 3 has a result to show: a draft, or a PDF made from one. */
const hasOutput = (i: JobStepsInput) => i.draft != null || i.pdf != null;

function outputSummary(i: JobStepsInput, state: StepState): string {
  const tailored = score(i.draft?.score ?? null);
  if (state === "next") {
    // Back on gaps after tailoring: the draft is still there until the next tailor.
    if (!hasOutput(i)) return "Review the changes, edit, Create PDF";
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
    const state: StepState = index < at ? "done" : index === at ? "current" : "next";
    const reachable = key === "output" ? hasOutput(input) : key === "qa" ? input.hasApplication : true;
    const summary =
      key === "job" ? jobSummary(input)
      : key === "fit" ? fitSummary(input, state)
      : key === "output" ? outputSummary(input, state)
      : applySummary(input, state);
    return { key, number: (index + 1) as Step["number"], title: TITLES[key], state, reachable, summary };
  });
}

type ScoreRow = { phase: string; target_id: string; composite: number };
type SessionRow = Pick<
  TailoringSession,
  "id" | "status" | "application_id" | "base_resume" | "created_at" | "gaps_json" | "resolutions_json"
>;

/**
 * `jobSteps`'s input from what the job page already holds: the detail (`job`, `application` and its
 * resume's name), the job's score rows, the header's score pill, the job's gap analyses, and what the
 * page words itself (the skills count and the knock-out words, both the Job details card's own reading;
 * the standing text). `baseName` names a base resume; `countGaps` is lib/gap-counts `gapCounts`, passed in
 * so this file keeps only type imports.
 */
export function jobStepsInput(a: {
  job: Pick<Job, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;
  application: Pick<Application, "id" | "base_resume" | "customized_json" | "pdf_path" | "pdf_pages"> | null;
  /** The detail's `base_resume_name` (null on an older backend: `baseName` names it then). */
  applicationResumeName: string | null;
  scoreRows: readonly ScoreRow[];
  scoreShown: { value: number; tailored: boolean } | null;
  sessions: readonly SessionRow[];
  skills: { total: number; required: number };
  knockout: string | null;
  standing: string;
  baseName: (slug: string) => string;
  countGaps: (gapIds: readonly string[], resolutions: SessionRow["resolutions_json"]) => GapCounts;
}): JobStepsInput {
  const { job, application, scoreRows, sessions, baseName } = a;
  const stage = job.stage ?? "saved";
  const baseScoreOf = (slug: string) =>
    scoreRows.find((s) => s.phase === "base" && s.target_id === slug)?.composite ?? null;
  const top = scoreRows.filter((s) => s.phase === "base").sort((x, y) => y.composite - x.composite)[0];
  const named = (slug: string | null) => ({ name: slug ? baseName(slug) : null, score: slug ? baseScoreOf(slug) : null });

  let base: JobStepsInput["base"];
  if (stage === "gaps") {
    // The open analysis's resume; the best base until the sessions list has loaded.
    base = named(sessions.find((s) => s.id === job.open_session_id)?.base_resume ?? top?.target_id ?? null);
  } else if (application && stage !== "saved" && stage !== "scored") {
    base = {
      name: a.applicationResumeName ?? baseName(application.base_resume),
      score: baseScoreOf(application.base_resume),
    };
  } else {
    base = { name: top ? baseName(top.target_id) : null, score: top?.composite ?? null };
  }

  // The analysis that made the draft: the application's newest tailored session.
  const madeDraft = application
    ? sessions
        .filter((s) => s.status === "tailored" && s.application_id === application.id)
        .sort((x, y) => y.created_at.localeCompare(x.created_at))[0]
    : undefined;

  return {
    stage,
    skills: a.skills,
    knockout: a.knockout,
    base,
    openGaps: stage === "gaps" ? { closed: job.gaps_done ?? 0, total: job.gaps_total ?? 0 } : null,
    draftGaps: madeDraft
      ? a.countGaps(
          madeDraft.gaps_json.categories.flatMap((c) => c.gaps.map((g) => g.gap_id)),
          madeDraft.resolutions_json,
        )
      : null,
    draft: application?.customized_json
      ? { score: a.scoreShown?.tailored ? a.scoreShown.value : null, changes: null }
      : null,
    // The application carries no render time, so the line says "PDF created" without a date.
    pdf: application?.pdf_path ? { pages: application.pdf_pages, createdOn: null } : null,
    standing: a.standing,
    hasApplication: application != null,
  };
}
