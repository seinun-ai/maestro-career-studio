import assert from "node:assert/strict";
import { test } from "node:test";

import type { Rung } from "./next-step.ts";
import { gapCounts } from "./gap-counts.ts";
import { currentStep, jobSteps, jobStepsInput, stepForTab, type JobStepsInput } from "./job-steps.ts";

const input = (over: Partial<JobStepsInput> = {}): JobStepsInput => ({
  stage: "scored",
  skills: { total: 14, required: 6 },
  knockout: "No knock-outs",
  base: { name: "Data scientist", score: 72.25 },
  openGaps: null,
  draftGaps: null,
  draft: null,
  pdf: null,
  standing: "Draft · not sent",
  hasApplication: false,
  ...over,
});
const summary = (over: Partial<JobStepsInput>, n: 1 | 2 | 3 | 4) => jobSteps(input(over))[n - 1].summary;
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
    tailored: "output", pdf_ready: "output",
    applied: "qa", closed: "qa",
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
  assert.deepEqual(states("pdf_ready"), ["done", "done", "current", "next"]);
  assert.deepEqual(states("applied"), ["done", "done", "done", "current"]);
  assert.deepEqual(states("closed"), ["done", "done", "done", "current"]);
});

test("step 1 names the skills and the knock-out words as given", () => {
  assert.equal(summary({ knockout: "A knock-out" }, 1), "14 skills, 6 required · A knock-out");
  assert.equal(summary({ knockout: "Requirements not checked" }, 1), "14 skills, 6 required · Requirements not checked");
  assert.equal(summary({ knockout: null }, 1), "14 skills, 6 required");
  assert.equal(summary({ skills: { total: 0, required: 0 } }, 1), "No skills found · No knock-outs");
  assert.equal(summary({ skills: { total: 1, required: 1 } }, 1), "1 skill, 1 required · No knock-outs");
});

test("step 2 current: no analysis, a session, a session with no gaps", () => {
  assert.equal(summary({ stage: "saved" }, 2), "Pick a resume and analyze its gaps");
  assert.equal(summary({ stage: "scored" }, 2), "Pick a resume and analyze its gaps");
  const open = (closed: number, total: number) => ({ closed, total });
  assert.equal(summary({ stage: "gaps", openGaps: open(3, 8) }, 2), "Data scientist · 3 of 8 gaps closed");
  assert.equal(summary({ stage: "gaps", openGaps: open(1, 1) }, 2), "Data scientist · 1 of 1 gap closed");
  assert.equal(summary({ stage: "gaps", openGaps: open(0, 0) }, 2), "Data scientist · no gaps found");
  assert.equal(summary({ stage: "gaps", base: { name: null, score: null }, openGaps: open(0, 0) }, 2), "No gaps found");
});

test("step 2 done: name, score, answered and skipped, null parts left out", () => {
  const done = { stage: "tailored" as const };
  assert.equal(summary({ ...done, draftGaps: gaps(5, 2, 8) }, 2), "Data scientist · 72.3 / 100 · 5 gaps answered, 2 skipped");
  assert.equal(summary({ ...done, draftGaps: gaps(1, 0, 1) }, 2), "Data scientist · 72.3 / 100 · 1 gap answered, 0 skipped");
  assert.equal(
    summary({ ...done, base: { name: "Data scientist", score: null }, draftGaps: gaps(5, 2, 8) }, 2),
    "Data scientist · 5 gaps answered, 2 skipped",
  );
  assert.equal(summary({ ...done, draftGaps: gaps(0, 0, 0) }, 2), "Data scientist · 72.3 / 100 · no gaps found");
  assert.equal(summary({ ...done, base: { name: null, score: 72.25 } }, 2), "72.3 / 100");
  assert.equal(summary({ ...done, base: { name: null, score: null } }, 2), "No gaps analyzed");
});

test("step 3 next: the hint while there is no draft", () => {
  assert.equal(summary({ stage: "gaps" }, 3), "Review the changes, edit, Create PDF");
  assert.equal(summary({ stage: "scored" }, 3), "Review the changes, edit, Create PDF");
});

const reach = (over: Partial<JobStepsInput>) => jobSteps(input(over)).map((s) => s.reachable);

test("a draft from before a re-analysis is next but reachable: no false tick, no lock", () => {
  const draft = { score: 84, changes: 7 };
  const over = { stage: "gaps" as const, openGaps: { closed: 1, total: 4 }, draft, hasApplication: true };
  const steps = jobSteps(input(over));
  assert.deepEqual(steps.map((s) => s.state), ["done", "current", "next", "next"]);
  assert.deepEqual(reach(over), [true, true, true, true]);
  assert.equal(steps[2].summary, "Draft from before, 84.0 / 100 · Tailor again to replace it");
  assert.equal(summary({ stage: "gaps", draft: { score: null, changes: null } }, 3), "Draft from before · Tailor again to replace it");
  // A PDF made from it counts too, and step 4 lists what is left.
  const pdf = { pages: 2, createdOn: null };
  assert.equal(jobSteps(input({ stage: "gaps", draft: null, pdf }))[2].reachable, true);
  assert.equal(summary({ stage: "gaps", draft, pdf }, 4), "Questions, cover letter, Mark applied");
  // Step 4 needs the application.
  assert.deepEqual(reach({ ...over, hasApplication: false }), [true, true, true, false]);
});

test("steps 3 and 4 open with what they show; before a draft only steps 1 and 2 do", () => {
  assert.deepEqual(reach({ stage: "saved" }), [true, true, false, false]);
  assert.deepEqual(reach({ stage: "scored" }), [true, true, false, false]);
  const draft = { score: 84, changes: 7 };
  assert.deepEqual(reach({ stage: "tailored", draft, hasApplication: true }), [true, true, true, true]);
  const pdf = { pages: 1, createdOn: null };
  assert.deepEqual(reach({ stage: "pdf_ready", draft, pdf, hasApplication: true }), [true, true, true, true]);
});

test("step 3 current without a PDF counts the changes to review", () => {
  assert.equal(summary({ stage: "tailored", draft: { score: 84, changes: 7 } }, 3), "7 changes to review · 84.0 / 100 · no PDF yet");
  assert.equal(summary({ stage: "tailored", draft: { score: null, changes: 1 } }, 3), "1 change to review · no PDF yet");
  assert.equal(summary({ stage: "tailored", draft: { score: 84, changes: 0 } }, 3), "No changes to review · 84.0 / 100 · no PDF yet");
  assert.equal(summary({ stage: "tailored", draft: { score: null, changes: null } }, 3), "No PDF yet");
});

test("step 3 with a PDF: pages when known, the date when known", () => {
  const draft = { score: 84, changes: 7 };
  assert.equal(
    summary({ stage: "pdf_ready", draft, pdf: { pages: 1, createdOn: "Oct 14" } }, 3),
    "84.0 / 100 · PDF created Oct 14, 1 page",
  );
  assert.equal(
    summary({ stage: "applied", draft, pdf: { pages: 2, createdOn: "Oct 14" } }, 3),
    "84.0 / 100 · PDF created Oct 14, 2 pages",
  );
  assert.equal(summary({ stage: "pdf_ready", draft, pdf: { pages: null, createdOn: "Oct 14" } }, 3), "84.0 / 100 · PDF created Oct 14");
  assert.equal(summary({ stage: "pdf_ready", draft: { score: null, changes: null }, pdf: { pages: null, createdOn: null } }, 3), "PDF created");
  assert.equal(summary({ stage: "pdf_ready", draft: null, pdf: { pages: null, createdOn: null } }, 3), "PDF created");
  assert.equal(summary({ stage: "applied", draft }, 3), "84.0 / 100 · no PDF");
  assert.equal(summary({ stage: "applied" }, 3), "No PDF");
});

test("step 4 waits on the PDF, then lists what is left; current reads the standing", () => {
  assert.equal(summary({ stage: "gaps" }, 4), "After Create PDF");
  assert.equal(summary({ stage: "tailored" }, 4), "After Create PDF");
  assert.equal(summary({ stage: "pdf_ready", pdf: { pages: 2, createdOn: "Oct 14" } }, 4), "Questions, cover letter, Mark applied");
  assert.equal(summary({ stage: "applied", standing: "Applied Oct 14 with Data scientist" }, 4), "Applied Oct 14 with Data scientist");
});

test("every summary is set, starts with a capital or a digit, and never prints null", () => {
  const stages: Rung[] = ["saved", "scored", "gaps", "tailored", "pdf_ready", "applied", "closed"];
  const cases: Partial<JobStepsInput>[] = [
    {},
    { knockout: null },
    { base: { name: null, score: null } },
    { base: { name: null, score: 50 } },
    { draftGaps: gaps(0, 0, 0), openGaps: { closed: 0, total: 0 } },
    { draftGaps: gaps(1, 0, 4), openGaps: { closed: 1, total: 4 } },
    { draftGaps: gaps(0, 0, 0), openGaps: { closed: 0, total: 0 }, base: { name: null, score: null } },
    { draft: null },
    { draft: { score: null, changes: null } },
    { draft: { score: 80, changes: 0 } },
    { draft: { score: null, changes: 0 } },
    { pdf: { pages: null, createdOn: null } },
    { pdf: { pages: 0, createdOn: null } },
    { skills: { total: 0, required: 0 } },
    {
      knockout: null, base: { name: null, score: null }, openGaps: null, draftGaps: null,
      draft: null, pdf: { pages: null, createdOn: null },
    },
  ];
  for (const stage of stages) {
    for (const c of cases) {
      for (const step of jobSteps(input({ ...c, stage }))) {
        const where = `${stage} ${step.key} ${JSON.stringify(c)}`;
        assert.doesNotMatch(step.summary, /null|undefined|NaN/, where);
        assert.match(step.summary, /^[A-Z0-9]/, where);
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

const app = { id: "a1", base_resume: "ds", customized_json: { x: 1 }, pdf_path: null, pdf_pages: null };
const rows = [
  { phase: "base", target_id: "ml", composite: 80 },
  { phase: "base", target_id: "ds", composite: 70 },
  { phase: "tailored", target_id: "a1", composite: 88 },
];
const built = (over: Partial<Parameters<typeof jobStepsInput>[0]> = {}) =>
  jobStepsInput({
    job: { stage: "tailored", open_session_id: null, gaps_done: 0, gaps_total: 0 },
    application: app,
    applicationResumeName: null,
    scoreRows: rows,
    scoreShown: { value: 88, tailored: true },
    sessions: [],
    skills: { total: 3, required: 1 },
    knockout: "No knock-outs",
    standing: "Not applied",
    baseName: (slug) => `Resume ${slug}`,
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

test("the resume on step 2: the open analysis's, the application's, or the best base", () => {
  const job = { stage: "gaps" as const, open_session_id: "o", gaps_done: 2, gaps_total: 5 };
  const open = session({ id: "o", status: "open", base_resume: "ds" });
  // gaps: the open analysis's resume, else the best base until the sessions load.
  assert.deepEqual(built({ job, sessions: [open] }).base, { name: "Resume ds", score: 70 });
  assert.deepEqual(built({ job, sessions: [] }).base, { name: "Resume ml", score: 80 });
  // A draft: the application's resume, its own name first.
  assert.deepEqual(built().base, { name: "Resume ds", score: 70 });
  assert.deepEqual(built({ applicationResumeName: "Data scientist" }).base, { name: "Data scientist", score: 70 });
  // Before a draft: the best base.
  const scored = { stage: "scored" as const, open_session_id: null, gaps_done: 0, gaps_total: 0 };
  assert.deepEqual(built({ job: scored, application: null }).base, { name: "Resume ml", score: 80 });
  assert.deepEqual(built({ job: scored, application: null, scoreRows: [] }).base, { name: null, score: null });
});

test("gaps on the current step are the detail's own count; other stages have none", () => {
  const job = { stage: "gaps" as const, open_session_id: "o", gaps_done: 2, gaps_total: 5 };
  assert.deepEqual(built({ job }).openGaps, { closed: 2, total: 5 });
  assert.equal(built().openGaps, null);
  assert.equal(jobSteps(built({ job, applicationResumeName: "Data scientist" }))[1].summary, "Resume ml · 2 of 5 gaps closed");
});

test("the draft, the PDF and the application are what the application holds", () => {
  assert.deepEqual(built().draft, { score: 88, changes: null });
  assert.equal(built({ application: { ...app, customized_json: null } }).draft, null);
  assert.equal(built({ scoreShown: { value: 70, tailored: false } }).draft?.score, null);
  assert.equal(built().pdf, null);
  assert.deepEqual(built({ application: { ...app, pdf_path: "x.pdf", pdf_pages: 2 } }).pdf, { pages: 2, createdOn: null });
  assert.equal(built().hasApplication, true);
  assert.equal(built({ application: null }).hasApplication, false);
  assert.equal(built({ job: { stage: undefined, open_session_id: null } }).stage, "saved");
});
