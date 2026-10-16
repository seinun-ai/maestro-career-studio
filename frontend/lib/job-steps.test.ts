import assert from "node:assert/strict";
import { test } from "node:test";

import type { Rung } from "./next-step.ts";
import { currentStep, jobSteps, stepForTab, type JobStepsInput } from "./job-steps.ts";

const input = (over: Partial<JobStepsInput> = {}): JobStepsInput => ({
  stage: "scored",
  skillsTotal: 14, requiredTotal: 6,
  knockout: "clear",
  resumeName: "Data scientist", baseScore: 72.25,
  gapsDone: 0, gapsSkipped: 0, gapsTotal: 0,
  tailoredScore: null, changes: null,
  pdfPages: null, pdfCreatedOn: null,
  standing: "Draft · not sent",
  ...over,
});
const summary = (over: Partial<JobStepsInput>, n: 1 | 2 | 3 | 4) => jobSteps(input(over))[n - 1].summary;
const states = (stage: Rung) => jobSteps(input({ stage })).map((s) => s.state);

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
  const steps = jobSteps(input());
  assert.deepEqual(steps.map((s) => [s.key, s.number, s.title]), [
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

test("step 1 names the skills and the knock-out scan's verdict", () => {
  assert.equal(summary({ knockout: "clear" }, 1), "14 skills, 6 required · no knock-outs");
  assert.equal(summary({ knockout: "conflict" }, 1), "14 skills, 6 required · a knock-out: see the job");
  assert.equal(summary({ knockout: "unstated" }, 1), "14 skills, 6 required · requirements not stated");
  assert.equal(summary({ knockout: null }, 1), "14 skills, 6 required · requirements not checked");
  assert.equal(summary({ skillsTotal: 0, requiredTotal: 0 }, 1), "No skills found · no knock-outs");
  assert.equal(summary({ skillsTotal: 1, requiredTotal: 1 }, 1), "1 skill, 1 required · no knock-outs");
});

test("step 2 current with and without a session, and done", () => {
  assert.equal(summary({ stage: "gaps", gapsDone: 3, gapsTotal: 8 }, 2), "Data scientist · 3 of 8 gaps closed");
  assert.equal(summary({ stage: "scored" }, 2), "Pick a resume and analyze its gaps");
  assert.equal(
    summary({ stage: "tailored", gapsDone: 5, gapsSkipped: 2, gapsTotal: 8 }, 2),
    "Data scientist · 72.3 · 5 gaps closed, 2 skipped",
  );
  assert.equal(
    summary({ stage: "tailored", baseScore: null, gapsDone: 5, gapsSkipped: 2, gapsTotal: 8 }, 2),
    "Data scientist · 5 gaps closed, 2 skipped",
  );
  assert.equal(summary({ stage: "tailored", gapsTotal: 0 }, 2), "Data scientist · 72.3");
  assert.equal(summary({ stage: "tailored", resumeName: null, gapsTotal: 0 }, 2), "72.3");
  assert.equal(summary({ stage: "tailored", resumeName: null, baseScore: null, gapsTotal: 0 }, 2), "No gaps analyzed");
});

test("step 3 as next, current without a PDF, and with one", () => {
  assert.equal(summary({ stage: "gaps" }, 3), "Review the changes, edit, Create PDF");
  assert.equal(
    summary({ stage: "tailored", changes: 7, tailoredScore: 84 }, 3),
    "7 changes to review · 84.0 · no PDF yet",
  );
  assert.equal(summary({ stage: "tailored", changes: 1, tailoredScore: null }, 3), "1 change to review · no PDF yet");
  assert.equal(
    summary({ stage: "pdf_ready", tailoredScore: 84, pdfPages: 1, pdfCreatedOn: "Oct 14" }, 3),
    "84.0 · PDF created Oct 14, 1 page",
  );
  assert.equal(
    summary({ stage: "applied", tailoredScore: 84, pdfPages: 2, pdfCreatedOn: "Oct 14" }, 3),
    "84.0 · PDF created Oct 14, 2 pages",
  );
  assert.equal(summary({ stage: "applied", tailoredScore: null }, 3), "No PDF");
});

test("step 4 waits on the PDF, then lists what is left; current reads the standing", () => {
  assert.equal(summary({ stage: "gaps" }, 4), "After Create PDF");
  assert.equal(summary({ stage: "tailored" }, 4), "After Create PDF");
  assert.equal(summary({ stage: "pdf_ready", pdfPages: 2 }, 4), "Questions, cover letter, Mark applied");
  assert.equal(summary({ stage: "applied", standing: "Applied Oct 14 with Data scientist" }, 4), "Applied Oct 14 with Data scientist");
});

test("no summary ever prints null or undefined", () => {
  const nullable = ["knockout", "resumeName", "baseScore", "tailoredScore", "changes", "pdfPages", "pdfCreatedOn"] as const;
  const stages: Rung[] = ["saved", "scored", "gaps", "tailored", "pdf_ready", "applied", "closed"];
  const allNull = Object.fromEntries(nullable.map((k) => [k, null])) as Partial<JobStepsInput>;
  const cases: Partial<JobStepsInput>[] = [allNull, ...nullable.map((k) => ({ [k]: null }))];
  for (const stage of stages) {
    for (const gapsTotal of [0, 4]) {
      for (const c of cases) {
        for (const step of jobSteps(input({ ...c, stage, gapsTotal, gapsDone: gapsTotal ? 1 : 0 }))) {
          assert.doesNotMatch(step.summary, /null|undefined|NaN/, `${stage} ${step.key} ${JSON.stringify(c)}`);
          assert.notEqual(step.summary, "", `${stage} ${step.key} ${JSON.stringify(c)}`);
        }
      }
    }
  }
});
