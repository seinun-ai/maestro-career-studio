import assert from "node:assert/strict";
import { test } from "node:test";

import type { Rung } from "./next-step.ts";
import { gapCounts } from "./gap-counts.ts";
import { currentStep, jobFacts, jobSteps, jobStepsInput, stepForTab, type JobStepsInput } from "./job-steps.ts";

const input = (over: Partial<JobStepsInput> = {}): JobStepsInput => ({
  stage: "scored",
  skills: { total: 14, required: 6 },
  openGaps: null,
  draftGaps: null,
  draft: null,
  pdf: false,
  hasApplication: false,
  ...over,
});
const metric = (over: Partial<JobStepsInput>, n: 1 | 2 | 3 | 4) => jobSteps(input(over))[n - 1].metric;
const progress = (over: Partial<JobStepsInput>, n: 1 | 2 | 3 | 4) => jobSteps(input(over))[n - 1].progress;
const states = (stage: Rung) => jobSteps(input({ stage })).map((s) => s.state);
const gaps = (answered: number, skipped: number, total: number) => ({ answered, skipped, open: total - answered - skipped, total });

test("each tab value the app has written maps to its step; anything else is the job", () => {
  assert.equal(stepForTab("jd"), "job");
  assert.equal(stepForTab("fit"), "fit");
  assert.equal(stepForTab("output"), "output");
  assert.equal(stepForTab("qa"), "qa");
  assert.equal(stepForTab("submitted"), "qa");
  assert.equal(stepForTab("nope"), "job");
  assert.equal(stepForTab(null), "job");
  assert.equal(stepForTab(undefined), "job");
});

test("object prototype keys and an empty tab are not steps", () => {
  assert.equal(stepForTab("__proto__"), "job");
  assert.equal(stepForTab("constructor"), "job");
  assert.equal(stepForTab(""), "job");
});

test("the current step follows the stage", () => {
  const want: Record<Rung, string> = {
    saved: "fit", scored: "fit", gaps: "fit",
    tailored: "output",
    pdf_ready: "qa", applied: "qa", closed: "qa",
  };
  for (const [stage, step] of Object.entries(want)) assert.equal(currentStep(stage as Rung), step, stage);
});

test("four numbered steps with their titles", () => {
  assert.deepEqual(jobSteps(input()).map((s) => [s.key, s.number, s.title]), [
    ["job", 1, "Job"], ["fit", 2, "Resume and gaps"], ["output", 3, "Tailored resume"], ["qa", 4, "Apply"],
  ]);
});

test("steps before the current one are done, the rest next", () => {
  assert.deepEqual(states("saved"), ["done", "current", "next", "next"]);
  assert.deepEqual(states("gaps"), ["done", "current", "next", "next"]);
  assert.deepEqual(states("tailored"), ["done", "done", "current", "next"]);
  // A made PDF is step 3 done: the job opens on Apply (owner, 2026-10-22).
  assert.deepEqual(states("pdf_ready"), ["done", "done", "done", "current"]);
  assert.deepEqual(states("applied"), ["done", "done", "done", "current"]);
  assert.deepEqual(states("closed"), ["done", "done", "done", "current"]);
});

test("step 1's number is the skills the job asks for", () => {
  assert.equal(metric({}, 1), "14 skills");
  assert.equal(metric({ skills: { total: 1, required: 1 } }, 1), "1 skill");
  assert.equal(metric({ skills: { total: 0, required: 0 } }, 1), "0 skills");
});

test("the Job description fold names the skills and the knock-out words as given", () => {
  assert.equal(jobFacts({ total: 14, required: 6 }, "A knock-out"), "14 skills, 6 required · A knock-out");
  assert.equal(jobFacts({ total: 14, required: 6 }, null), "14 skills, 6 required");
  assert.equal(jobFacts({ total: 0, required: 0 }, "No knock-outs"), "No skills found · No knock-outs");
  assert.equal(jobFacts({ total: 1, required: 1 }, null), "1 skill, 1 required");
});

test("step 2 current: gaps closed of all, nothing before an analysis", () => {
  assert.equal(metric({ stage: "saved" }, 2), null);
  assert.equal(metric({ stage: "scored" }, 2), null);
  const open = (closed: number, total: number) => ({ closed, total });
  assert.equal(metric({ stage: "gaps", openGaps: open(3, 8) }, 2), "3 of 8 closed");
  assert.equal(metric({ stage: "gaps", openGaps: open(1, 1) }, 2), "1 of 1 closed");
  assert.equal(metric({ stage: "gaps", openGaps: open(0, 0) }, 2), "0 gaps");
  assert.equal(progress({ stage: "gaps", openGaps: open(3, 8) }, 2), 3 / 8);
  // No share to fill: the bar marks the step and claims none.
  assert.equal(progress({ stage: "gaps", openGaps: open(0, 0) }, 2), null);
  assert.equal(progress({ stage: "scored" }, 2), null);
});

test("step 2 done: the gaps of the analysis that made the draft", () => {
  const done = { stage: "tailored" as const };
  assert.equal(metric({ ...done, draftGaps: gaps(5, 2, 8) }, 2), "7 of 8 closed");
  assert.equal(metric({ ...done, draftGaps: gaps(6, 0, 6) }, 2), "6 of 6 closed");
  assert.equal(metric({ ...done, draftGaps: gaps(0, 0, 0) }, 2), "0 gaps");
  // Used as is, with no analysis: no number to show.
  assert.equal(metric({ ...done, draftGaps: null }, 2), null);
  assert.equal(progress({ ...done, draftGaps: null }, 2), 1);
});

test("step 3: the base resume's score and the tailored one, or the tailored one alone, or nothing", () => {
  assert.equal(metric({ stage: "gaps" }, 3), null);
  assert.equal(metric({ stage: "tailored", draft: { score: 84, base: 72.25 } }, 3), "72.3 → 84.0");
  assert.equal(metric({ stage: "tailored", draft: { score: 84, base: null } }, 3), "84.0");
  assert.equal(metric({ stage: "tailored", draft: { score: null, base: 72 } }, 3), null);
  // The draft from before a re-analysis still says what it scored.
  assert.equal(metric({ stage: "gaps", draft: { score: 84, base: 70 } }, 3), "70.0 → 84.0");
  // Current: no share before the PDF; done (full) once it exists.
  assert.equal(progress({ stage: "tailored", draft: { score: 84, base: 70 } }, 3), null);
  assert.equal(progress({ stage: "pdf_ready", draft: { score: 84, base: 70 }, pdf: true }, 3), 1);
});

test("step 4 has no number; full once applied or closed, no share while you apply", () => {
  for (const stage of ["saved", "gaps", "tailored", "pdf_ready", "applied", "closed"] as Rung[]) {
    assert.equal(metric({ stage, hasApplication: true, pdf: true }, 4), null, stage);
  }
  assert.equal(progress({ stage: "applied", hasApplication: true }, 4), 1);
  assert.equal(progress({ stage: "closed", hasApplication: true }, 4), 1);
  assert.equal(progress({ stage: "pdf_ready", hasApplication: true, pdf: true }, 4), null);
  assert.equal(progress({ stage: "tailored", hasApplication: true }, 4), 0);
});

const reach = (over: Partial<JobStepsInput>) => jobSteps(input(over)).map((s) => s.reachable);

test("a draft from before a re-analysis is next but reachable: no false tick, no lock", () => {
  const draft = { score: 84, base: 70 };
  const over = { stage: "gaps" as const, openGaps: { closed: 1, total: 4 }, draft, hasApplication: true };
  const steps = jobSteps(input(over));
  assert.deepEqual(steps.map((s) => s.state), ["done", "current", "next", "next"]);
  assert.deepEqual(reach(over), [true, true, true, true]);
  // A PDF made from it counts too.
  assert.equal(jobSteps(input({ stage: "gaps", draft: null, pdf: true }))[2].reachable, true);
  // Step 4 needs the application.
  assert.deepEqual(reach({ ...over, hasApplication: false }), [true, true, true, false]);
});

test("steps 3 and 4 open with what they show; before a draft only steps 1 and 2 do", () => {
  assert.deepEqual(reach({ stage: "saved" }), [true, true, false, false]);
  assert.deepEqual(reach({ stage: "scored" }), [true, true, false, false]);
  const draft = { score: 84, base: 70 };
  assert.deepEqual(reach({ stage: "tailored", draft, hasApplication: true }), [true, true, true, true]);
  assert.deepEqual(reach({ stage: "pdf_ready", draft, pdf: true, hasApplication: true }), [true, true, true, true]);
});

test("a done step is full, a later one empty, and no number ever prints null", () => {
  const stages: Rung[] = ["saved", "scored", "gaps", "tailored", "pdf_ready", "applied", "closed"];
  const cases: Partial<JobStepsInput>[] = [
    {},
    { draftGaps: gaps(0, 0, 0), openGaps: { closed: 0, total: 0 } },
    { draftGaps: gaps(1, 0, 4), openGaps: { closed: 1, total: 4 } },
    { draft: { score: null, base: null } },
    { draft: { score: 80, base: null } },
    { pdf: true },
    { skills: { total: 0, required: 0 } },
  ];
  for (const stage of stages) {
    for (const c of cases) {
      for (const step of jobSteps(input({ ...c, stage }))) {
        const where = `${stage} ${step.key} ${JSON.stringify(c)}`;
        if (step.metric !== null) assert.doesNotMatch(step.metric, /null|undefined|NaN/, where);
        if (step.state === "done") assert.equal(step.progress, 1, where);
        if (step.state === "next") assert.equal(step.progress, 0, where);
        if (step.progress !== null) assert.ok(step.progress >= 0 && step.progress <= 1, where);
      }
    }
  }
});

// ── jobStepsInput: the page's data, read the same way every time ──────────────────

const session = (over: Record<string, unknown>) => ({
  id: "s1",
  status: "tailored" as const,
  application_id: "a1",
  base_resume: "ds",
  created_at: "2026-10-01T00:00:00Z",
  gaps_json: { categories: [{ gaps: [{ gap_id: "g1" }, { gap_id: "g2" }, { gap_id: "g3" }] }] },
  resolutions_json: [{ gap_id: "g1", action: "add_keyword" }],
  ...over,
}) as unknown as Parameters<typeof jobStepsInput>[0]["sessions"][number];

const app = { id: "a1", base_resume: "ds", customized_json: { x: 1 }, pdf_path: null };
const rows = [
  { phase: "base", target_id: "ml", composite: 80 },
  { phase: "base", target_id: "ds", composite: 70 },
  { phase: "tailored", target_id: "a1", composite: 88 },
];
const built = (over: Partial<Parameters<typeof jobStepsInput>[0]> = {}) =>
  jobStepsInput({
    rung: { stage: "tailored", open_session_id: null, gaps_done: 0, gaps_total: 0 },
    application: app,
    scoreRows: rows,
    scoreShown: { value: 88, tailored: true },
    sessions: [],
    skills: { total: 3, required: 1 },
    countGaps: gapCounts,
    ...over,
  });

test("the draft's gaps come from the application's newest tailored session", () => {
  const older = session({ id: "old", created_at: "2026-09-01T00:00:00Z", resolutions_json: [] });
  const newer = session({ id: "new", created_at: "2026-10-02T00:00:00Z", resolutions_json: [
    { gap_id: "g1", action: "add_keyword" }, { gap_id: "g2", action: "skip" },
  ] });
  const open = session({ id: "o", status: "open", created_at: "2026-10-03T00:00:00Z" });
  const other = session({ id: "x", application_id: "a2", created_at: "2026-10-04T00:00:00Z" });
  assert.deepEqual(built({ sessions: [older, newer, open, other] }).draftGaps, { answered: 1, skipped: 1, open: 1, total: 3 });
  assert.equal(built({ sessions: [open, other] }).draftGaps, null);
  assert.equal(built({ application: null, sessions: [newer] }).draftGaps, null);
});

test("gaps on the current step are the detail's own count; other stages have none", () => {
  const rung = { stage: "gaps" as const, open_session_id: "o", gaps_done: 2, gaps_total: 5 };
  assert.deepEqual(built({ rung }).openGaps, { closed: 2, total: 5 });
  assert.equal(built().openGaps, null);
  assert.equal(jobSteps(built({ rung }))[1].metric, "2 of 5 closed");
});

test("the draft, its base resume's score, the PDF and the application are what the application holds", () => {
  // The tailored score and the score of the base resume the draft came from (ds, not the best base ml).
  assert.deepEqual(built().draft, { score: 88, base: 70 });
  assert.equal(jobSteps(built())[2].metric, "70.0 → 88.0");
  assert.equal(built({ application: { ...app, customized_json: null } }).draft, null);
  assert.equal(built({ scoreShown: { value: 70, tailored: false } }).draft?.score, null);
  assert.equal(built({ scoreRows: [] }).draft?.base, null);
  assert.equal(built().pdf, false);
  assert.equal(built({ application: { ...app, pdf_path: "x.pdf" } }).pdf, true);
  assert.equal(built().hasApplication, true);
  assert.equal(built({ application: null }).hasApplication, false);
  assert.equal(built({ rung: { stage: undefined, open_session_id: null } }).stage, "saved");
});

test("the steps read the rung from the detail, where it sits beside the job", () => {
  const detail = { job: { id: "j1", title: "Analyst" }, stage: "applied" as const, open_session_id: null, gaps_done: 0, gaps_total: 0 };
  assert.equal(built({ rung: detail }).stage, "applied");
  // The nested job alone carries no stage: read that way, every job looked saved.
  assert.equal(built({ rung: detail.job as never }).stage, "saved");
  const gaps = { job: {}, stage: "gaps" as const, open_session_id: "s1", gaps_done: 2, gaps_total: 5 };
  assert.deepEqual(built({ rung: gaps }).openGaps, { closed: 2, total: 5 });
});

test("on the gap page, step 2's number is the analysis on screen, whatever the stage", () => {
  // An applied job tailored from an earlier analysis (1 of 3 closed) while the page shows a new one: the number
  // and the footer below it count the same analysis.
  const made = session({ id: "made" });
  const applied = { stage: "applied" as const, open_session_id: null, gaps_done: 0, gaps_total: 0 };
  const shown = {
    base_resume: "ml",
    gapIds: ["g1", "g2", "g3", "g4"],
    resolutions: [{ gap_id: "g1", action: "add_keyword" }, { gap_id: "g2", action: "skip" }],
  };
  assert.equal(jobSteps(built({ rung: applied, sessions: [made] }))[1].metric, "1 of 3 closed");
  const steps = jobSteps(built({ rung: applied, sessions: [made], shown }));
  assert.equal(steps[1].metric, "2 of 4 closed");
  assert.equal(steps[1].state, "done"); // the stage still says where the job is
  // Another open analysis than the server's newest: the page's, counted from its own answers as they change.
  const gaps = { stage: "gaps" as const, open_session_id: "o", gaps_done: 2, gaps_total: 5 };
  assert.equal(jobSteps(built({ rung: gaps, shown }))[1].metric, "2 of 4 closed");
  assert.equal(jobSteps(built({ rung: gaps, shown }))[1].progress, 2 / 4);
  assert.equal(jobSteps(built({ rung: gaps, shown: { ...shown, gapIds: [], resolutions: [] } }))[1].metric, "0 gaps");
  // No analysis on screen (the job page): the stage's count as before.
  assert.equal(jobSteps(built({ rung: gaps, shown: null }))[1].metric, "2 of 5 closed");
});
