import assert from "node:assert/strict";
import { test } from "node:test";

import { headerProposalPill, historyLabel, proposalCanExpire, proposalHasContent, historyStatusOf, isNew, isReady, readinessMarks, readinessSteps, readyFirst } from "./inbox-readiness.ts";

const ready = { tailored: true, knockout: null, to_check: 0 };

test("ready is tailored, no knock-out, nothing to check", () => {
  assert.equal(isReady(ready), true);
  assert.equal(isReady({ ...ready, tailored: false }), false);
  assert.equal(isReady({ ...ready, tailored: null }), false);
  assert.equal(isReady({ ...ready, knockout: "opt" }), false);
  assert.equal(isReady({ ...ready, to_check: 1 }), false);
  assert.equal(isReady({ ...ready, base_country: "US" }), false);
  assert.equal(isReady({ ...ready, base_country: null }), true);
  assert.equal(isReady(null), false);
  assert.equal(isReady(undefined), false);
});

test("a resume for another country is marked after the knock-out and before what to check", () => {
  assert.deepEqual(readinessMarks({ ...ready, base_country: "US" }), [
    { text: "Resume for another country", tone: "warning" },
  ]);
  assert.deepEqual(readinessMarks({ tailored: false, knockout: "opt", to_check: 2, base_country: "US" }), [
    { text: "Knock-out: OPT", tone: "error" },
    { text: "Resume for another country", tone: "warning" },
    { text: "2 to check", tone: "warning" },
  ]);
  assert.deepEqual(readinessMarks({ ...ready, base_country: null }), []);
});

test("marks say the knock-out (a conflict, error tone) and what to check (warning)", () => {
  assert.deepEqual(readinessMarks({ tailored: false, knockout: "on_site", to_check: 3 }), [
    { text: "Knock-out: on-site", tone: "error" },
    { text: "3 to check", tone: "warning" },
  ]);
  assert.deepEqual(readinessMarks(ready), []);
  assert.deepEqual(readinessMarks({ tailored: null, knockout: "new_kind", to_check: 0 }), [
    { text: "Knock-out", tone: "error" },
  ]);
  assert.deepEqual(readinessMarks(null), []);
  assert.deepEqual(readinessMarks(undefined), []);
});

for (const [kind, word] of [
  ["work_authorization", "work authorization"],
  ["opt", "OPT"],
  ["salary", "salary"],
  ["experience", "experience"],
  ["on_site", "on-site"],
]) {
  test(`the ${kind} knock-out has a readable label`, () => {
    assert.deepEqual(readinessMarks({ tailored: null, knockout: kind, to_check: 0 }), [
      { text: `Knock-out: ${word}`, tone: "error" },
    ]);
  });
}

test("ready rows come first and keep their order", () => {
  const rows = [
    { id: "a", readiness: { ...ready, tailored: false } },
    { id: "b", readiness: ready },
    { id: "c", readiness: null },
    { id: "d", readiness: ready },
  ];
  assert.deepEqual(readyFirst(rows).map((r) => r.id), ["b", "d", "a", "c"]);
});

test("sorting keeps older rows without readiness and leaves the input untouched", () => {
  const rows = Object.freeze([
    { id: "older" },
    { id: "ready", readiness: ready },
    { id: "warning", readiness: { ...ready, to_check: 1 } },
  ]);
  const sorted = readyFirst(rows);
  assert.deepEqual(sorted.map((r) => r.id), ["ready", "older", "warning"]);
  assert.deepEqual(rows.map((r) => r.id), ["older", "ready", "warning"]);
  assert.equal(sorted[0], rows[1]);
  assert.deepEqual(readyFirst([]), []);
});

test("a job the user applied to themselves reads Applied yourself", () => {
  assert.equal(historyLabel("rejected", "applied manually", "Skipped"), "Applied yourself");
  assert.equal(historyLabel("rejected", "not a fit", "Skipped"), "Skipped");
  assert.equal(historyLabel("submitted", null, "Applied"), "Applied");
  assert.equal(historyLabel("submitted", "applied manually", "Applied"), "Applied");
  assert.equal(historyLabel("rejected", undefined, "Skipped"), "Skipped");
});

test("manual applies are grouped under Applied in History filters", () => {
  assert.equal(historyStatusOf("rejected", "applied manually"), "submitted");
  assert.equal(historyStatusOf("rejected", "not a fit"), "rejected");
  assert.equal(historyStatusOf("rejected", null), "rejected");
  assert.equal(historyStatusOf("submitted", "applied manually"), "submitted");
});

test("new means created after the last visit", () => {
  assert.equal(isNew("2026-10-05T10:00:00Z", "2026-10-05T09:00:00Z"), true);
  assert.equal(isNew("2026-10-05T08:00:00Z", "2026-10-05T09:00:00Z"), false);
  assert.equal(isNew("2026-10-05T10:00:00Z", null), false);
});

test("visit comparisons use instants and do not mark equal or invalid dates new", () => {
  assert.equal(isNew("2026-10-05T10:00:00Z", "2026-10-05T10:00:00Z"), false);
  assert.equal(isNew("2026-10-05T05:00:00-05:00", "2026-10-05T09:00:00Z"), true);
  assert.equal(isNew("2026-10-05T10:00:00Z", "2026-10-05T05:00:00-05:00"), false);
  assert.equal(isNew("2026-10-05T10:00:00Z", "invalid saved visit"), false);
  assert.equal(isNew("invalid created date", "2026-10-05T09:00:00Z"), false);
});

test("readiness steps count what is done", () => {
  assert.equal(readinessSteps(null), null);
  assert.deepEqual(readinessSteps({ tailored: true, knockout: null, to_check: 0 }), { done: 3, total: 3 });
  assert.deepEqual(readinessSteps({ tailored: false, knockout: "opt", to_check: 2 }), { done: 0, total: 3 });
  assert.deepEqual(readinessSteps({ tailored: null, knockout: null, to_check: 1 }), { done: 1, total: 3 });
  // A resume for another country blocks like a knock-out: the meter is never full on a row that is not ready.
  assert.deepEqual(readinessSteps({ tailored: true, knockout: null, to_check: 0, base_country: "US" }), { done: 2, total: 3 });
  assert.deepEqual(readinessSteps({ tailored: true, knockout: "opt", to_check: 0, base_country: "US" }), { done: 2, total: 3 });
});

test("the job header shows one status: an application's, never the proposal pill beside it", () => {
  assert.equal(
    headerProposalPill({ hasApplication: true, status: "rejected", reason: "applied manually", fallbackLabel: "Skipped" }),
    null,
  );
  assert.equal(headerProposalPill({ hasApplication: true, status: "accepted", reason: null, fallbackLabel: "Queued" }), null);
});

test("with no application the header pill reads like the inbox History lane", () => {
  assert.deepEqual(
    headerProposalPill({ hasApplication: false, status: "rejected", reason: "applied manually", fallbackLabel: "Skipped" }),
    { label: "Applied yourself", styleStatus: "submitted" },
  );
  assert.deepEqual(
    headerProposalPill({ hasApplication: false, status: "rejected", reason: "not a fit", fallbackLabel: "Skipped" }),
    { label: "Skipped", styleStatus: "rejected" },
  );
  assert.deepEqual(
    headerProposalPill({ hasApplication: false, status: "accepted", reason: undefined, fallbackLabel: "Queued" }),
    { label: "Queued", styleStatus: "accepted" },
  );
  assert.equal(headerProposalPill({ hasApplication: false, status: null, reason: null, fallbackLabel: "" }), null);
});

const filed = {
  status: "accepted",
  reason: null,
  proposed_by: "you",
  plan_json: { summary: "Queued from the Companion by the user" },
  qa_entries: [],
  evidence_json: [],
};

test("a proposal you filed with only the fixed plan carries nothing", () => {
  assert.equal(proposalHasContent(filed), false);
  assert.equal(proposalHasContent({ ...filed, plan_json: { summary: "Promoted from the tracker by the user" } }), false);
  assert.equal(proposalHasContent({ ...filed, plan_json: null, evidence_json: null }), false);
});

test("each thing a proposal can carry makes the card worth showing", () => {
  assert.equal(proposalHasContent({ ...filed, status: "needs_decision" }), true); // a question
  assert.equal(proposalHasContent({ ...filed, status: "needs_human" }), true); // a stop
  assert.equal(proposalHasContent({ ...filed, status: "rejected", reason: "not a fit" }), true);
  assert.equal(proposalHasContent({ ...filed, plan_json: { company_note: "Acme is hiring" } }), true);
  assert.equal(proposalHasContent({ ...filed, plan_json: { summary: "Lead with the SQL work" } }), true);
  assert.equal(proposalHasContent({ ...filed, qa_entries: [{ id: "q1" }] }), true);
  assert.equal(proposalHasContent({ ...filed, evidence_json: [{ path: "evidence/step1.png" }] }), true);
});

test("an agent's own fixed-looking plan is still its plan", () => {
  assert.equal(
    proposalHasContent({ ...filed, proposed_by: "claude-code", plan_json: { summary: "Queued from the Companion by the user" } }),
    true,
  );
});

test("empty strings and non-screenshot evidence do not count", () => {
  assert.equal(proposalHasContent({ ...filed, plan_json: { summary: "  ", company_note: "" }, reason: " " }), false);
  assert.equal(proposalHasContent({ ...filed, evidence_json: [{ path: "/jobs/42" }, { path: "" }] }), false);
});

test("an applied-manually skip is history the Where this stands line already tells", () => {
  assert.equal(proposalHasContent({ ...filed, status: "rejected", reason: "applied manually" }), false);
});

test("only a proposal that is still open can expire", () => {
  assert.equal(proposalCanExpire("pending_review"), true);
  assert.equal(proposalCanExpire("needs_decision"), true);
  for (const status of ["needs_human", "accepted", "approved", "submitted", "submission_uncertain", "rejected", "expired"]) {
    assert.equal(proposalCanExpire(status), false, status);
  }
});
