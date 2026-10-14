import assert from "node:assert/strict";
import { test } from "node:test";

import { scorePill, standingLine } from "./job-standing.ts";

const base = (target_id: string, composite: number) => ({
  phase: "base", target_id, composite, application_id: null, created_at: "2026-10-01T10:00:00Z",
});
const tailored = (composite: number, created_at: string, application_id = "app-1") => ({
  phase: "tailored", target_id: "app-1", composite, application_id, created_at,
});

test("a tailored score reads Resume match, tailored", () => {
  const pill = scorePill([base("a", 70), base("b", 82), tailored(91, "2026-10-02T10:00:00Z")], "app-1");
  assert.deepEqual(pill, { label: "Resume match", value: 91, targetId: "app-1", tailored: true });
});

test("the newest tailored score of the application wins", () => {
  const pill = scorePill([tailored(80, "2026-10-02T10:00:00Z"), tailored(88, "2026-10-03T10:00:00Z")], "app-1");
  assert.equal(pill?.value, 88);
});

test("only base scores read Best base resume, the highest", () => {
  const pill = scorePill([base("a", 70), base("b", 82)], null);
  assert.deepEqual(pill, { label: "Best base resume", value: 82, targetId: "b", tailored: false });
});

test("a tailored score of another application does not count", () => {
  const pill = scorePill([base("a", 70), tailored(99, "2026-10-02T10:00:00Z", "other")], "app-1");
  assert.equal(pill?.label, "Best base resume");
});

test("neither score, no pill", () => {
  assert.equal(scorePill([], null), null);
  assert.equal(scorePill([], "app-1"), null);
});

const draft = { status: "draft", applied_at: null, pdf_path: null };
const none = { hasFilledAnswers: false, appliedOn: null, resumeName: null, bestBase: null };

test("an applied job says when, with which resume, and links its PDF and receipt", () => {
  const line = standingLine({
    application: { ...draft, status: "applied", applied_at: "2026-10-03T12:00:00Z", pdf_path: "x.pdf" },
    appliedOn: "Oct 3",
    resumeName: "Data Scientist",
    bestBase: { name: "Other", value: 70 },
    hasFilledAnswers: true,
  });
  assert.deepEqual(line, {
    kind: "applied",
    text: "Applied Oct 3 with Data Scientist resume",
    pdf: true,
    submitted: true,
  });
});

test("an applied job leaves out the links it has nothing for", () => {
  const line = standingLine({
    application: { ...draft, status: "interviewing", applied_at: "2026-10-03T12:00:00Z" },
    appliedOn: "Oct 3",
    resumeName: "Data Scientist",
    bestBase: null,
    hasFilledAnswers: false,
  });
  assert.deepEqual(line, { kind: "applied", text: "Applied Oct 3 with Data Scientist resume", pdf: false, submitted: false });
});

test("applied with no date or resume name still reads whole", () => {
  const line = standingLine({
    application: { ...draft, status: "applied", applied_at: null },
    appliedOn: null,
    resumeName: null,
    bestBase: null,
    hasFilledAnswers: false,
  });
  assert.equal(line.text, "Applied");
});

test("a rejected application that was applied to still says it was applied", () => {
  const line = standingLine({
    application: { ...draft, status: "rejected", applied_at: "2026-10-03T12:00:00Z" },
    appliedOn: "Oct 3",
    resumeName: "Data Scientist",
    bestBase: null,
    hasFilledAnswers: false,
  });
  assert.equal(line.kind, "applied");
});

test("a draft says it is not applied and names the best resume", () => {
  const line = standingLine({ application: draft, appliedOn: null, resumeName: null, bestBase: { name: "Data Scientist", value: 82.14 }, hasFilledAnswers: false });
  assert.deepEqual(line, { kind: "draft", text: "Not applied · best resume Data Scientist 82.1", pdf: false, submitted: false });
});

test("a draft with no score says only that it is not applied", () => {
  assert.equal(standingLine({ application: draft, ...none }).text, "Not applied");
});

test("no application: not applied yet, with the best base resume when scored", () => {
  assert.deepEqual(standingLine({ application: null, appliedOn: null, resumeName: null, bestBase: { name: "ML Engineer", value: 77 }, hasFilledAnswers: false }), {
    kind: "none",
    text: "Not applied yet · best resume ML Engineer 77.0",
    pdf: false,
    submitted: false,
  });
  assert.equal(standingLine({ application: null, ...none }).text, "Not applied yet");
});

test("a job filled but never marked applied still links what was submitted", () => {
  assert.equal(standingLine({ application: null, appliedOn: null, resumeName: null, bestBase: null, hasFilledAnswers: true }).submitted, true);
});
