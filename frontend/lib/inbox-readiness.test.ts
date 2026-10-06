import assert from "node:assert/strict";
import { test } from "node:test";

import { historyLabel, historyStatusOf, isNew, isReady, readinessMarks, readinessSteps, readyFirst } from "./inbox-readiness.ts";

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
