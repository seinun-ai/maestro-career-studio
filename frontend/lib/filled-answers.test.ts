import assert from "node:assert/strict";
import { test } from "node:test";

import { allAnswersToggle, answerPreview, latestAnswers } from "./filled-answers.ts";
import type { FilledField, FilledStep } from "./types";

const field = (question: string, over: Partial<FilledField> = {}): FilledField => ({
  question,
  section: null,
  required: false,
  answer: "Yes",
  options_count: null,
  source: "profile",
  slot: null,
  eeo: false,
  eeo_answered: false,
  edited_by_you: false,
  version: null,
  flags: [],
  ...over,
});
const page = (captured_at: string, fields: FilledField[]): FilledStep => ({
  step: null, host: null, channel: "companion", captured_at, sections: [{ section: null, fields }],
});
const receipt = (steps: FilledStep[]) => ({
  job_id: "j", host: "jobs.example.com", pages: steps.length, captured_at: null, flag_count: 0, steps,
});

test("the newest page's answers come first, and the count is every answer the receipt holds", () => {
  const r = receipt([
    page("2026-10-01T10:00:00Z", [field("Name"), field("Email")]),
    page("2026-10-02T10:00:00Z", [field("Why us?")]),
  ]);
  const { fields, total } = latestAnswers(r, 2);
  assert.deepEqual(fields.map((f) => f.question), ["Why us?", "Name"]);
  assert.equal(total, 3);
});

test("a voluntary answer is counted but never shown on the card", () => {
  const r = receipt([page("2026-10-01T10:00:00Z", [field("Gender", { eeo: true }), field("Name")])]);
  const { fields, total } = latestAnswers(r, 3);
  assert.deepEqual(fields.map((f) => f.question), ["Name"]);
  assert.equal(total, 2);
});

test("an answer reads as one short line", () => {
  assert.equal(answerPreview(field("Skills", { answer: ["SQL", "Python"] })), "SQL, Python");
  assert.equal(answerPreview(field("Middle name", { answer: "  " })), "Left blank");
  assert.equal(answerPreview(field("Resume", { source: "upload", slot: "resume", answer: "cv.pdf" })), "Resume attached: cv.pdf");
  assert.equal(
    answerPreview(field("Letter", { source: "upload", slot: "cover_letter", answer: "letter.pdf" })),
    "Cover letter attached: letter.pdf",
  );
});

test("the link names the count, and one answer is not called all", () => {
  assert.equal(allAnswersToggle(12, false), "All 12 answers");
  assert.equal(allAnswersToggle(12, true), "Hide all answers");
  assert.equal(allAnswersToggle(1, false), "Show it in full");
});
