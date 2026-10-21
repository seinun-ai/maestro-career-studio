import assert from "node:assert/strict";
import { test } from "node:test";

import { scorePill, standingLine, statusDate } from "./job-standing.ts";

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
const standing0 = { application: null, appliedOn: null, resumeName: null, tailored: false, hasFilledAnswers: false, proposal: null };
const sent = { ...draft, status: "applied", applied_at: "2026-10-03T12:00:00Z" };

test("an applied job says when and with which resume, and links its PDF and receipt", () => {
  const line = standingLine({
    ...standing0, application: { ...sent, pdf_path: "x.pdf" }, appliedOn: "Oct 3", resumeName: "Data Scientist", hasFilledAnswers: true,
  });
  assert.deepEqual(line, {
    kind: "applied", text: "Applied Oct 3 with Data Scientist resume", pdf: true, submitted: true,
  });
});

test("a tailored resume is said once, with its name and no score", () => {
  const line = standingLine({ ...standing0, application: sent, appliedOn: "Oct 3", resumeName: "Data Scientist", tailored: true });
  assert.equal(line.text, "Applied Oct 3 with Data Scientist resume, tailored");
});

test("an applied job leaves out the links it has nothing for", () => {
  const line = standingLine({ ...standing0, application: { ...sent, status: "interviewing" }, appliedOn: "Oct 3", resumeName: "Data Scientist" });
  assert.deepEqual(line, { kind: "applied", text: "Applied Oct 3 with Data Scientist resume", pdf: false, submitted: false });
});

test("applied with no date or resume name still reads whole", () => {
  assert.equal(standingLine({ ...standing0, application: { ...sent, applied_at: null } }).text, "Applied");
});

test("a rejected application that was applied to still says it was applied", () => {
  const line = standingLine({ ...standing0, application: { ...sent, status: "rejected" }, appliedOn: "Oct 3" });
  assert.equal(line.kind, "applied");
});

test("a draft names its resume", () => {
  const line = standingLine({ ...standing0, application: draft, resumeName: "Data Scientist" });
  assert.deepEqual(line, { kind: "draft", text: "Not applied · Data Scientist resume", pdf: false, submitted: false });
  assert.equal(standingLine({ ...standing0, application: draft, resumeName: "Data Scientist", tailored: true }).text,
    "Not applied · Data Scientist resume, tailored");
  assert.equal(standingLine({ ...standing0, application: draft }).text, "Not applied");
});

test("a draft with an open proposal says where the proposal is", () => {
  const words: Record<string, string> = {
    pending_review: "Not applied · waiting for your review in the Agent inbox",
    accepted: "Not applied · queued for your agent",
    approved: "Not applied · your agent is applying",
    needs_decision: "Not applied · your agent needs you (below)",
    needs_human: "Not applied · your agent needs you (below)",
  };
  for (const [status, text] of Object.entries(words)) {
    const line = standingLine({ ...standing0, application: draft, resumeName: "Data Scientist", proposal: { status, yourself: false, on: null } });
    assert.equal(line.text, text, status);
    assert.equal(line.kind, "draft");
  }
});

test("a closed proposal that was skipped or expired leaves the draft's ordinary line", () => {
  for (const status of ["rejected", "expired"]) {
    const line = standingLine({ ...standing0, application: draft, resumeName: "Data Scientist", proposal: { status, yourself: false, on: null } });
    assert.equal(line.text, "Not applied · Data Scientist resume", status);
  }
});

test("no application: not applied yet, with no score to repeat", () => {
  assert.deepEqual(standingLine(standing0), { kind: "none", text: "Not applied yet", pdf: false, submitted: false });
});

test("a job filled but never marked applied still links what was submitted", () => {
  assert.equal(standingLine({ ...standing0, hasFilledAnswers: true }).submitted, true);
});

test("no application, but the proposal records an application that went out", () => {
  const submitted = standingLine({ ...standing0, proposal: { status: "submitted", yourself: false, on: "Oct 4" } });
  assert.deepEqual(submitted, { kind: "applied", text: "Applied Oct 4", pdf: false, submitted: false });
  const yourself = standingLine({ ...standing0, proposal: { status: "submitted", yourself: true, on: "Oct 4" } });
  assert.equal(yourself.kind, "applied");
  assert.equal(yourself.text, "Applied yourself Oct 4");
  assert.equal(standingLine({ ...standing0, proposal: { status: "submitted", yourself: true, on: null } }).text, "Applied yourself");
});

test("an application set back to Draft is not applied, whatever its old proposal says", () => {
  const line = standingLine({
    ...standing0, application: { ...draft, pdf_path: "x.pdf" }, resumeName: "Data Scientist",
    proposal: { status: "submitted", yourself: true, on: "Oct 4" },
  });
  assert.equal(line.kind, "draft");
  assert.equal(line.pdf, false);
  assert.equal(line.text, "Not applied · Data Scientist resume");
});

test("a draft whose submit the agent could not confirm says so", () => {
  const line = standingLine({
    ...standing0, application: draft, resumeName: "Data Scientist",
    proposal: { status: "submission_uncertain", yourself: false, on: null },
  });
  assert.equal(line.text, "Not applied · your agent isn't sure it went through: check the Agent inbox");
  assert.equal(line.kind, "draft");
});

test("the Jobs row dates its status: when it began from the log, Applied by the date you applied", () => {
  const row = (status: string | null, applied_at: string | null, status_since?: string | null) => ({ status, applied_at, status_since });
  // Interviewing since the log's change into it.
  assert.deepEqual(statusDate(row("interviewing", "2026-09-01", "2026-09-10")), { at: "2026-09-10", word: "Since" });
  // Applied reads the applied date, which you can set, even when the log has its own time.
  assert.deepEqual(statusDate(row("applied", "2026-09-01", "2026-09-03")), { at: "2026-09-01", word: "Applied" });
  assert.deepEqual(statusDate(row("applied", null, "2026-09-03")), { at: "2026-09-03", word: "Since" });
  // A status older than the log: the applied date, as before, else nothing (never a guess).
  assert.deepEqual(statusDate(row("rejected", "2026-09-01", null)), { at: "2026-09-01", word: "Applied" });
  assert.equal(statusDate(row("interviewing", null, null)), null);
  assert.equal(statusDate(row("interviewing", null)), null);
  // A draft has no status worth dating.
  assert.equal(statusDate(row("draft", null, "2026-09-03")), null);
  assert.equal(statusDate(row(null, null, "2026-09-03")), null);
});
