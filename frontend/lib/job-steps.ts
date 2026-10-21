/**
 * The job page's four steps as data: which one is current from the server's stage, the one number each
 * shows (no sentences: "18 skills", "6 of 6 closed", "72.3 → 84.0") and how full its bar is. Pure, so
 * `node --test` loads it; it imports only types, which the loader erases (a value import would need a
 * `.ts` path, which tsc rejects).
 */
import type { GapCounts } from "./gap-counts";
import type { Rung } from "./next-step";
import type { Application, JobDetail, TailoringSession } from "./types";

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
 * `metric`: the step's one number from the data, or null where the data has none (never a made-up one).
 * `progress`: the bar's fill from 0 to 1. A done step is full and a later one empty; the current one is its
 * own share where the data says one (gaps closed of all, a PDF made, the job applied or closed) and null where
 * it says none: the bar then marks the step without claiming a share.
 */
export type Step = {
  key: StepKey;
  number: 1 | 2 | 3 | 4;
  title: string;
  state: StepState;
  reachable: boolean;
  metric: string | null;
  progress: number | null;
};

/**
 * The current step from the stage: saved/scored/gaps → fit; tailored/pdf_ready → output; applied/closed → qa.
 * Never "job": the job exists once saved, so step 1 is always done and step 2 is never next. A rung that
 * would make the job step current is a deliberate change here.
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

type Closed = { closed: number; total: number };

export type JobStepsInput = {
  stage: Rung;
  skills: { total: number; required: number };
  /** The open gap analysis's count while step 2 is current (the server's: closed = answered or skipped); null = none. */
  openGaps: Closed | null;
  /** The gap page's analysis, counted from its answers on screen: step 2's number counts it whatever the stage. */
  shownGaps?: Closed | null;
  /** The gaps of the analysis that made the draft, for a done step 2 (lib/gap-counts); null = none. */
  draftGaps: GapCounts | null;
  /** Null = no draft (the application's customized_json is absent). `score` is its tailored Match score and
   *  `base` the score of the base resume it came from; either is null until it is scored. */
  draft: { score: number | null; base: number | null } | null;
  /** The application has a PDF (its pdf_path): step 3 has made what it makes. */
  pdf: boolean;
  /** The job has an application: step 4 has a panel. */
  hasApplication: boolean;
};

const TITLES: Record<StepKey, string> = { job: "Job", fit: "Resume and gaps", output: "Tailored resume", qa: "Apply" };

/** The parts that are set, joined, the first letter capitalised. */
function join(...parts: (string | null)[]): string {
  const line = parts.filter((p): p is string => !!p).join(" · ");
  return line.charAt(0).toUpperCase() + line.slice(1);
}
const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const score = (n: number) => n.toFixed(1);

/** The Job description fold's line: the skills and the knock-out card's words ("18 skills, 11 required · No knock-outs"). */
export function jobFacts(skills: { total: number; required: number }, knockout: string | null): string {
  const found = skills.total > 0
    ? `${count(skills.total, "skill", "skills")}, ${skills.required} required`
    : "No skills found";
  return join(found, knockout);
}

/** Step 2's gaps: the analysis on the gap page, else the one that made the draft once done, else the open one. */
function fitGaps(i: JobStepsInput, state: StepState): Closed | null {
  if (i.shownGaps) return i.shownGaps;
  if (state === "done") {
    const g = i.draftGaps;
    return g ? { closed: g.answered + g.skipped, total: g.total } : null;
  }
  return i.openGaps;
}

/** Step 3's number: the base resume's score and the tailored one ("72.3 → 84.0"), the tailored one alone without
 *  a base score, nothing before the draft is scored. */
function outputMetric(i: JobStepsInput): string | null {
  const tailored = i.draft?.score ?? null;
  if (tailored == null) return null;
  const base = i.draft?.base ?? null;
  return base == null ? score(tailored) : `${score(base)} → ${score(tailored)}`;
}

/** Step 3 has a result to show: a draft, or a PDF made from one. */
const hasOutput = (i: JobStepsInput) => i.draft != null || i.pdf;

function progressOf(key: StepKey, state: StepState, i: JobStepsInput, gaps: Closed | null): number | null {
  if (state === "done") return 1;
  if (state === "next") return 0;
  if (key === "fit") return gaps && gaps.total > 0 ? gaps.closed / gaps.total : null;
  if (key === "output") return i.pdf ? 1 : null;
  // Step 4 is current only once the job is applied or closed (currentStep).
  if (key === "qa") return 1;
  return null;
}

export function jobSteps(input: JobStepsInput): Step[] {
  const at = STEP_KEYS.indexOf(currentStep(input.stage));
  return STEP_KEYS.map((key, index) => {
    const state: StepState = index < at ? "done" : index === at ? "current" : "next";
    const reachable = key === "output" ? hasOutput(input) : key === "qa" ? input.hasApplication : true;
    const gaps = key === "fit" ? fitGaps(input, state) : null;
    const metric =
      key === "job" ? count(input.skills.total, "skill", "skills")
      : key === "fit" ? (gaps ? (gaps.total === 0 ? "0 gaps" : `${gaps.closed} of ${gaps.total} closed`) : null)
      : key === "output" ? outputMetric(input)
      : null;
    return {
      key,
      number: (index + 1) as Step["number"],
      title: TITLES[key],
      state,
      reachable,
      metric,
      progress: progressOf(key, state, input, gaps),
    };
  });
}

type ScoreRow = { phase: string; target_id: string; composite: number };
type SessionRow = Pick<
  TailoringSession,
  "id" | "status" | "application_id" | "base_resume" | "created_at" | "gaps_json" | "resolutions_json"
>;

/**
 * `jobSteps`'s input from what the job page already holds: the detail (its rung and `application`), the job's
 * score rows, the header's score pill and the job's gap analyses. `countGaps` is lib/gap-counts `gapCounts`,
 * passed in so this file keeps only type imports.
 */
export function jobStepsInput(a: {
  /** The detail itself: `GET /api/jobs/{id}/detail` sends the rung and the open gap analysis beside `job`, not in
   *  it (JobDetail's `job` has no stage, so a page that read `detail.job.stage` saw every job as saved). */
  rung: Pick<JobDetail, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;
  application: Pick<Application, "id" | "base_resume" | "customized_json" | "pdf_path"> | null;
  scoreRows: readonly ScoreRow[];
  scoreShown: { value: number; tailored: boolean } | null;
  sessions: readonly SessionRow[];
  skills: { total: number; required: number };
  countGaps: (gapIds: readonly string[], resolutions: SessionRow["resolutions_json"]) => GapCounts;
  /** The gap page's analysis: its resume, its gaps and the answers on screen (the page's working copy). */
  shown?: { base_resume: string; gapIds: readonly string[]; resolutions: SessionRow["resolutions_json"] } | null;
}): JobStepsInput {
  const { rung, application, scoreRows, sessions } = a;
  const stage = rung.stage ?? "saved";
  const baseScoreOf = (slug: string) =>
    scoreRows.find((s) => s.phase === "base" && s.target_id === slug)?.composite ?? null;

  const shownCounts = a.shown ? a.countGaps(a.shown.gapIds, a.shown.resolutions) : null;

  // The analysis that made the draft: the application's newest tailored session.
  const madeDraft = application
    ? sessions
        .filter((s) => s.status === "tailored" && s.application_id === application.id)
        .sort((x, y) => y.created_at.localeCompare(x.created_at))[0]
    : undefined;

  return {
    stage,
    skills: a.skills,
    openGaps: stage === "gaps" ? { closed: rung.gaps_done ?? 0, total: rung.gaps_total ?? 0 } : null,
    shownGaps: shownCounts ? { closed: shownCounts.answered + shownCounts.skipped, total: shownCounts.total } : null,
    draftGaps: madeDraft
      ? a.countGaps(
          madeDraft.gaps_json.categories.flatMap((c) => c.gaps.map((g) => g.gap_id)),
          madeDraft.resolutions_json,
        )
      : null,
    draft: application?.customized_json
      ? {
          score: a.scoreShown?.tailored ? a.scoreShown.value : null,
          base: baseScoreOf(application.base_resume),
        }
      : null,
    // A draft change removes the PDF on the server, so a PDF that exists is the draft's own.
    pdf: Boolean(application?.pdf_path),
    hasApplication: application != null,
  };
}
