import assert from "node:assert/strict";
import { test } from "node:test";

import { countsLine, outcomeWord, proposedLine, recentRefusals, recentRunsSummary, reportLine, runsByAutomation } from "./agent-runs.ts";

test("counts read number first in a fixed order, zeros left out", () => {
  assert.equal(countsLine({ skipped: 8, found: 12, proposed: 4, updated: 0 }), "12 found, 4 proposed, 8 skipped");
  assert.equal(countsLine({ needs_you: 1 }), "1 needs you");
  assert.equal(countsLine({ needs_you: 2, tailored: 3 }), "3 tailored, 2 need you");
  assert.equal(countsLine({}), "Nothing to report");
});

test("every supported count has a place and unknown keys are left out", () => {
  assert.equal(countsLine({ needs_you: 2, skipped: 5, updated: 4, tailored: 3, proposed: 2, found: 1 }),
    "1 found, 2 proposed, 3 tailored, 4 updated, 5 skipped, 2 need you");
  assert.equal(countsLine({ found: 0, needs_you: 0 }), "Nothing to report");
  assert.equal(countsLine({ unknown: 8, updated: 1 }), "1 updated");
});

test("outcomes in words", () => {
  assert.equal(outcomeWord("ok"), "Done");
  assert.equal(outcomeWord("partial"), "Partly done");
  assert.equal(outcomeWord("failed"), "Failed");
});

test("runs grouped by automation keep the list's newest-first order", () => {
  const runs = [
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z" },
    { automation: "job-hunt", finished_at: "2026-10-03T10:00:00Z" },
  ];
  const map = runsByAutomation(runs);
  assert.deepEqual([...map.keys()], ["job-hunt", "mail-status"]);
  assert.deepEqual(map.get("job-hunt")?.map((r) => r.finished_at), ["2026-10-05T10:00:00Z", "2026-10-03T10:00:00Z"]);
  assert.equal(map.get("unreported"), undefined);
  assert.equal(runsByAutomation([]).size, 0);
});

test("a card's report line: when, what the counts say, and who sent it", () => {
  const ago = (iso: string) => {
    assert.equal(iso, "2026-10-05T10:00:00Z");
    return "2 hours ago";
  };
  const run = (counts: Record<string, number>, on_bot = false) => ({ finished_at: "2026-10-05T10:00:00Z", counts, on_bot });
  assert.equal(reportLine(run({ updated: 3 }), "Claude", ago), "2 hours ago · 3 updated · by Claude");
  assert.equal(reportLine(run({ found: 12, proposed: 4 }, true), "Claude", ago),
    "2 hours ago · 12 found, 4 proposed · by Claude on your bot");
  // No counts say nothing, and an unknown agent is not named.
  assert.equal(reportLine(run({ found: 0 }), null, ago), "2 hours ago");
  assert.equal(reportLine(run({}, true), null, ago), "2 hours ago · on your bot");
  // An older backend does not send on_bot.
  assert.equal(reportLine({ finished_at: "2026-10-05T10:00:00Z", counts: { tailored: 2 } }, null, ago), "2 hours ago · 2 tailored");
});

test("the Recent runs row says how many it lists and how many did not finish", () => {
  assert.equal(recentRunsSummary([]), null);
  assert.equal(recentRunsSummary([{ outcome: "ok" }, { outcome: "ok" }]), "2");
  assert.equal(recentRunsSummary([{ outcome: "ok" }, { outcome: "failed" }, { outcome: "partial" }]),
    "3 · 1 failed, 1 partly done");
  assert.equal(recentRunsSummary([{ outcome: "partial" }]), "1 · 1 partly done");
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
