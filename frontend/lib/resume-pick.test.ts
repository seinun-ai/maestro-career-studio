import assert from "node:assert/strict";
import { test } from "node:test";

import { asIsOverDraftConfirm, defaultResumePick, finishedAnalysis, jobResumeState, switchConfirm } from "./resume-pick.ts";

const open = (base: string, at: string) => ({ base_resume: base, status: "open", created_at: at });
const app = (over: Partial<{ id: string; base_resume: string; status: string | null; customized_json: unknown }> = {}) => ({
  id: "app-1",
  base_resume: "ds",
  status: "draft",
  customized_json: { basics: {} },
  ...over,
});

test("the newest open gap analysis's resume wins", () => {
  const pick = defaultResumePick({
    sessions: [open("ds", "2026-10-01"), open("ml", "2026-10-03"), { ...open("ba", "2026-10-09"), status: "tailored" }],
    application: { base_resume: "ba" },
    best: "pm",
    available: ["pm", "ml", "ds", "ba"],
  });
  assert.equal(pick, "ml");
});

test("then the application's resume, then the best match", () => {
  assert.equal(defaultResumePick({ sessions: [], application: { base_resume: "ba" }, best: "pm", available: ["pm", "ba"] }), "ba");
  assert.equal(defaultResumePick({ sessions: [], application: null, best: "pm", available: ["pm", "ba"] }), "pm");
});

test("a resume with no chip (archived, another country) never becomes the pick", () => {
  const pick = defaultResumePick({
    sessions: [open("old", "2026-10-09")],
    application: { base_resume: "old" },
    best: "pm",
    available: ["pm", "ba"],
  });
  assert.equal(pick, "pm");
  assert.equal(defaultResumePick({ sessions: [], application: null, best: null, available: [] }), null);
});

test("the job's resume state: applied, tailored, used as is, or nothing", () => {
  assert.equal(jobResumeState(null, []), null);
  assert.equal(jobResumeState(app({ status: "applied" }), []), "applied");
  assert.equal(jobResumeState(app(), [{ base_resume: "ml", status: "tailored", created_at: "x", application_id: "app-1" }]), "tailored");
  assert.equal(jobResumeState(app(), [{ base_resume: "ds", status: "tailored", created_at: "x" }]), "tailored");
  // A tailored analysis of another base for another application says nothing about this one.
  assert.equal(jobResumeState(app(), [{ base_resume: "ml", status: "tailored", created_at: "x", application_id: "app-2" }]), "as_is");
  assert.equal(jobResumeState(app({ customized_json: null }), []), null);
});

test("each state has its own words, and the same resume asks nothing", () => {
  const base = { from: "Data Scientist", to: "ML Engineer", fromSlug: "ds", toSlug: "ml" } as const;
  const tailored = switchConfirm({ ...base, state: "tailored", action: "analyze" });
  assert.deepEqual(tailored, {
    title: "Switch to ML Engineer?",
    description:
      "This job already has a tailored Data Scientist resume. Tailoring with another resume replaces that draft and removes its PDF. " +
      "Version history keeps the old one. Answers you gave in the gaps for Data Scientist stay with it.",
    confirmLabel: "Switch and analyze gaps",
  });
  assert.equal(
    switchConfirm({ ...base, state: "as_is", action: "continue" })?.description,
    "This job's resume is Data Scientist, used as is. Tailoring with another resume replaces it and removes its PDF. Version history keeps the old one.",
  );
  assert.equal(switchConfirm({ ...base, state: "as_is", action: "continue" })?.confirmLabel, "Switch and continue");
  assert.equal(
    switchConfirm({ ...base, state: "applied", action: "as_is" })?.description,
    "You applied with Data Scientist. Using another resume as is replaces that resume and its PDF. Version history keeps them.",
  );
  assert.equal(
    switchConfirm({ ...base, state: "applied", action: "analyze" })?.description,
    "You applied with Data Scientist. Tailoring with another resume replaces that resume and its PDF. Version history keeps them.",
  );
  assert.equal(switchConfirm({ ...base, state: "applied", action: "as_is" })?.confirmLabel, "Switch and use as is");
  assert.equal(switchConfirm({ ...base, state: null, action: "analyze" }), null);
  assert.equal(switchConfirm({ ...base, toSlug: "ds", state: "tailored", action: "analyze" }), null);
});

test("once applied, the gap page's Tailor on the same resume asks; starting or opening an analysis does not", () => {
  const same = { from: "Data Scientist", to: "Data Scientist", fromSlug: "ds", toSlug: "ds" } as const;
  const again = {
    title: "Tailor Data Scientist again?",
    description: "You applied with Data Scientist. Tailoring again replaces that resume and its PDF. Version history keeps them.",
    confirmLabel: "Tailor again",
  };
  assert.deepEqual(switchConfirm({ ...same, state: "applied", action: "tailor" }), again);
  // Analyze gaps and Continue replace nothing; Use resume as is asks with asIsOverDraftConfirm.
  for (const action of ["analyze", "continue", "as_is"] as const) {
    assert.equal(switchConfirm({ ...same, state: "applied", action }), null, action);
  }
  // Before applying, the same resume asks nothing: the draft is still a draft.
  assert.equal(switchConfirm({ ...same, state: "tailored", action: "tailor" }), null);
  assert.equal(switchConfirm({ ...same, state: "as_is", action: "analyze" }), null);
  // Another resume at Tailor asks nothing: Analyze gaps or Continue asked on the way to the gap page.
  for (const state of ["applied", "tailored", "as_is"] as const) {
    assert.equal(switchConfirm({ ...same, to: "ML Engineer", toSlug: "ml", state, action: "tailor" }), null, state);
  }
  assert.deepEqual(asIsOverDraftConfirm(false), {
    title: "Replace the existing tailored draft?",
    description:
      "Using your base resume as is replaces this job's tailored resume and removes its PDF. Version history keeps the old one.",
    confirmLabel: "Replace draft",
  });
  assert.equal(asIsOverDraftConfirm(true).title, "Replace the existing tailored resume?");
  assert.equal(asIsOverDraftConfirm(true).confirmLabel, "Replace resume");
});

const done = (id: string, base: string, at: string, over: Record<string, unknown> = {}) => ({
  id, base_resume: base, status: "tailored", created_at: at, application_id: "app-1", ...over,
});

test("the job's tailored resume shows the analysis that made it, not a fresh Analyze gaps", () => {
  const sessions = [
    done("old", "ds", "2026-10-01"),
    done("new", "ds", "2026-10-05"),
    // Closed or replaced analyses made no draft; a newer one never hides the one that did.
    { ...done("closed", "ds", "2026-10-09"), status: "abandoned", application_id: null },
    { ...done("replaced", "ds", "2026-10-08"), status: "superseded", application_id: null },
  ];
  assert.equal(finishedAnalysis({ sessions, application: app(), picked: "ds" })?.id, "new");
});

test("no finished analysis for another resume, no draft, or an analysis of another application", () => {
  const sessions = [done("s", "ds", "2026-10-05")];
  assert.equal(finishedAnalysis({ sessions, application: app(), picked: "ml" }), null);
  assert.equal(finishedAnalysis({ sessions, application: null, picked: "ds" }), null);
  assert.equal(finishedAnalysis({ sessions, application: app({ customized_json: null }), picked: "ds" }), null);
  assert.equal(finishedAnalysis({ sessions, application: app({ id: "app-2" }), picked: "ds" }), null);
  // The application took another resume since: the analysis tailored "ds", the job's resume is "ml".
  assert.equal(finishedAnalysis({ sessions, application: app({ base_resume: "ml" }), picked: "ml" }), null);
  assert.equal(finishedAnalysis({ sessions: [], application: app(), picked: "ds" }), null);
});
