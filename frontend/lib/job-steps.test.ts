import assert from "node:assert/strict";
import { test } from "node:test";

import type { Rung } from "./next-step.ts";
import { currentStep, jobSteps, stepForTab, type JobStepsInput } from "./job-steps.ts";

const input = (over: Partial<JobStepsInput> = {}): JobStepsInput => ({
  stage: "scored",
  skills: { total: 14, required: 6 },
  knockout: "No knock-outs",
  base: { name: "Data scientist", score: 72.25 },
  gaps: null,
  draft: null,
  pdf: null,
  standing: "Draft · not sent",
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
  assert.equal(summary({ stage: "gaps", gaps: gaps(2, 1, 8) }, 2), "Data scientist · 3 of 8 gaps closed");
  assert.equal(summary({ stage: "gaps", gaps: gaps(0, 1, 1) }, 2), "Data scientist · 1 of 1 gap closed");
  assert.equal(summary({ stage: "gaps", gaps: gaps(0, 0, 0) }, 2), "Data scientist · no gaps found");
  assert.equal(summary({ stage: "gaps", base: { name: null, score: null }, gaps: gaps(0, 0, 0) }, 2), "No gaps found");
});

test("step 2 done: name, score, answered and skipped, null parts left out", () => {
  const done = { stage: "tailored" as const };
  assert.equal(summary({ ...done, gaps: gaps(5, 2, 8) }, 2), "Data scientist · 72.3 / 100 · 5 gaps answered, 2 skipped");
  assert.equal(summary({ ...done, gaps: gaps(1, 0, 1) }, 2), "Data scientist · 72.3 / 100 · 1 gap answered, 0 skipped");
  assert.equal(
    summary({ ...done, base: { name: "Data scientist", score: null }, gaps: gaps(5, 2, 8) }, 2),
    "Data scientist · 5 gaps answered, 2 skipped",
  );
  assert.equal(summary({ ...done, gaps: gaps(0, 0, 0) }, 2), "Data scientist · 72.3 / 100 · no gaps found");
  assert.equal(summary({ ...done, base: { name: null, score: 72.25 } }, 2), "72.3 / 100");
  assert.equal(summary({ ...done, base: { name: null, score: null } }, 2), "No gaps analyzed");
});

test("step 3 next: the hint while there is no draft", () => {
  assert.equal(summary({ stage: "gaps" }, 3), "Review the changes, edit, Create PDF");
  assert.equal(summary({ stage: "scored" }, 3), "Review the changes, edit, Create PDF");
});

test("a draft from before a re-analysis keeps step 3 done, so it stays reachable", () => {
  const draft = { score: 84, changes: 7 };
  const steps = jobSteps(input({ stage: "gaps", gaps: gaps(1, 0, 4), draft }));
  assert.deepEqual(steps.map((s) => s.state), ["done", "current", "done", "next"]);
  assert.equal(steps[2].summary, "Draft from before, 84.0 / 100 · Tailor again to replace it");
  assert.equal(summary({ stage: "gaps", draft: { score: null, changes: null } }, 3), "Draft from before · Tailor again to replace it");
  // A PDF made from it counts too, and step 4 lists what is left.
  const pdf = { pages: 2, createdOn: null };
  assert.equal(jobSteps(input({ stage: "gaps", draft, pdf }))[2].state, "done");
  assert.equal(summary({ stage: "gaps", draft, pdf }, 4), "Questions, cover letter, Mark applied");
  // Step 4 is never done ahead of the stage: its result is the stage itself.
  assert.equal(jobSteps(input({ stage: "tailored", draft, pdf }))[3].state, "next");
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
    { gaps: gaps(0, 0, 0) },
    { gaps: gaps(1, 0, 4) },
    { gaps: gaps(0, 0, 0), base: { name: null, score: null } },
    { draft: null },
    { draft: { score: null, changes: null } },
    { draft: { score: 80, changes: 0 } },
    { draft: { score: null, changes: 0 } },
    { pdf: { pages: null, createdOn: null } },
    { pdf: { pages: 0, createdOn: null } },
    { skills: { total: 0, required: 0 } },
    {
      knockout: null, base: { name: null, score: null }, gaps: null,
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
