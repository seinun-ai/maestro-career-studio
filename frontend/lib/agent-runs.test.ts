import assert from "node:assert/strict";
import { test } from "node:test";

import { countsLine, lastRanLine, latestByAutomation, proposedLine, recentRefusals, outcomeWord } from "./agent-runs.ts";

test("counts read in a fixed order, zeros left out", () => {
  assert.equal(countsLine({ skipped: 8, found: 12, proposed: 4, updated: 0 }),
    "Found 12 · proposed 4 · skipped 8");
  assert.equal(countsLine({ needs_you: 1 }), "1 needs you");
  assert.equal(countsLine({ needs_you: 2, tailored: 3 }), "Tailored 3 · 2 need you");
  assert.equal(countsLine({}), "Nothing to report");
});

test("every supported count has a place and unknown keys are left out", () => {
  assert.equal(countsLine({ needs_you: 2, skipped: 5, updated: 4, tailored: 3, proposed: 2, found: 1 }),
    "Found 1 · proposed 2 · tailored 3 · updated 4 · skipped 5 · 2 need you");
  assert.equal(countsLine({ found: 0, needs_you: 0 }), "Nothing to report");
  assert.equal(countsLine({ unknown: 8, updated: 1 }), "Updated 1");
});

test("outcomes in words", () => {
  assert.equal(outcomeWord("ok"), "Done");
  assert.equal(outcomeWord("partial"), "Partly done");
  assert.equal(outcomeWord("failed"), "Failed");
});

test("the newest run per automation, and the card's line", () => {
  const map = latestByAutomation([
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z", outcome: "partial" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z", outcome: "ok" },
  ]);
  assert.deepEqual(map.get("job-hunt"), { finished_at: "2026-10-05T10:00:00Z", outcome: "partial" });
  assert.equal(lastRanLine(undefined, (x) => x), null);
  assert.equal(lastRanLine(null, (x) => x), "Not run yet");
  assert.equal(lastRanLine("t", () => "2 hours ago"), "Last ran 2 hours ago");
});

test("an older run of the same automation does not replace its newest time", () => {
  const map = latestByAutomation([
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z", outcome: "ok" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z", outcome: "failed" },
    { automation: "job-hunt", finished_at: "2026-10-03T10:00:00Z", outcome: "failed" },
  ]);
  assert.deepEqual([...map], [
    ["job-hunt", { finished_at: "2026-10-05T10:00:00Z", outcome: "ok" }],
    ["mail-status", { finished_at: "2026-10-04T10:00:00Z", outcome: "failed" }],
  ]);
  assert.equal(map.get("unreported"), undefined);
  assert.equal(latestByAutomation([]).size, 0);
});

test("a card formats only a known finish time", () => {
  const ago = (iso: string) => {
    assert.equal(iso, "2026-10-05T10:00:00Z");
    return "2 hours ago";
  };
  assert.equal(lastRanLine(undefined, ago), null);
  assert.equal(lastRanLine(null, ago), "Not run yet");
  assert.equal(lastRanLine("2026-10-05T10:00:00Z", ago), "Last ran 2 hours ago");
});

const hunt = (proposed: number, over: Record<string, unknown> = {}) => ({
  title: "Job hunt", finished_at: "2026-10-05T10:00:00Z", counts: { proposed }, ...over,
});

test("the inbox says the newest run proposed jobs, and links to the runs", () => {
  assert.equal(proposedLine([hunt(4)], () => "2 hours ago"), "Job hunt proposed 4 jobs 2 hours ago");
  assert.equal(proposedLine([hunt(1)], () => "yesterday"), "Job hunt proposed 1 job yesterday");
});

test("the inbox says nothing when the newest run proposed nothing", () => {
  assert.equal(proposedLine([hunt(0)], () => "now"), null);
  // Found is not proposed: jobs saved but filed nowhere are not in the inbox.
  assert.equal(proposedLine([hunt(0, { counts: { found: 12 } })], () => "now"), null);
  assert.equal(proposedLine([], () => "now"), null);
  // The newest run decides: an older run's proposals are not news.
  assert.equal(proposedLine([hunt(0), hunt(9)], () => "now"), null);
});

const NOW = Date.parse("2026-10-14T12:00:00Z");
const refused = (answered_at: string | null) => ({ id: answered_at ?? "none", answered_at });

test("only refusals since the last visit show, and none older than a week", () => {
  const rows = [refused("2026-10-14T08:00:00Z"), refused("2026-10-12T08:00:00Z"), refused("2026-10-01T08:00:00Z")];
  assert.deepEqual(recentRefusals(rows, "2026-10-13T00:00:00Z", NOW).map((r) => r.id), ["2026-10-14T08:00:00Z"]);
  // With no visit known the week is the window.
  assert.deepEqual(recentRefusals(rows, null, NOW).map((r) => r.id), ["2026-10-14T08:00:00Z", "2026-10-12T08:00:00Z"]);
  // A long-ago visit never widens the window past a week.
  assert.deepEqual(recentRefusals(rows, "2026-09-01T00:00:00Z", NOW).map((r) => r.id), ["2026-10-14T08:00:00Z", "2026-10-12T08:00:00Z"]);
});

test("a refusal with no answer time is kept", () => {
  assert.equal(recentRefusals([refused(null)], "2026-10-13T00:00:00Z", NOW).length, 1);
});
