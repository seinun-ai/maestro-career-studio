import assert from "node:assert/strict";
import { test } from "node:test";

import { answersSummary } from "./filled-answers.ts";
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

test("the Autofill answers fold counts the answers your profile gave, else every answer", () => {
  const r = receipt([
    page("2026-10-01T10:00:00Z", [field("Name"), field("Email"), field("Why us?", { source: "written" })]),
    page("2026-10-02T10:00:00Z", [field("Gender", { eeo: true })]),
  ]);
  assert.equal(answersSummary(r), "3 from your profile");
  const one = receipt([page("2026-10-01T10:00:00Z", [field("Name")])]);
  assert.equal(answersSummary(one), "1 from your profile");
  const none = receipt([page("2026-10-01T10:00:00Z", [field("Why us?", { source: "written" }), field("CV", { source: "upload" })])]);
  assert.equal(answersSummary(none), "2 answers");
  assert.equal(answersSummary(receipt([])), null);
});

test("a page with several sections counts every answer", () => {
  const r = receipt([
    {
      step: null,
      host: null,
      channel: "companion",
      captured_at: "2026-10-01T10:00:00Z",
      sections: [
        { section: "Contact", fields: [field("Name", { source: "you" })] },
        { section: "Questions", fields: [field("Why us?", { source: "written" }), field("Gender", { eeo: true, source: "you" })] },
      ],
    },
  ]);
  assert.equal(answersSummary(r), "3 answers");
});
