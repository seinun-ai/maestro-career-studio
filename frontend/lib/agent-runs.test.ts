import assert from "node:assert/strict";
import { test } from "node:test";

import { countsLine, lastRanLine, latestByAutomation, outcomeWord } from "./agent-runs.ts";

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
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z" },
  ]);
  assert.equal(map.get("job-hunt"), "2026-10-05T10:00:00Z");
  assert.equal(lastRanLine(undefined, (x) => x), null);
  assert.equal(lastRanLine(null, (x) => x), "Not run yet");
  assert.equal(lastRanLine("t", () => "2 hours ago"), "Last ran 2 hours ago");
});

test("an older run of the same automation does not replace its newest time", () => {
  const map = latestByAutomation([
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z" },
    { automation: "job-hunt", finished_at: "2026-10-03T10:00:00Z" },
  ]);
  assert.deepEqual([...map], [
    ["job-hunt", "2026-10-05T10:00:00Z"],
    ["mail-status", "2026-10-04T10:00:00Z"],
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
