import { test } from "node:test";
import assert from "node:assert/strict";
import { STRIP_DAYS, dayStrip, dayStripLabel, reportedInStrip } from "./day-strip.ts";

test("one cell per local day, the worst outcome wins a day, empty days stay empty", () => {
  const today = new Date("2026-10-20T12:00:00");
  const runs = [
    { finished_at: "2026-10-20T08:00:00", outcome: "ok" as const },
    { finished_at: "2026-10-20T09:00:00", outcome: "partial" as const },
    { finished_at: "2026-10-18T09:00:00", outcome: "failed" as const },
  ];
  const cells = dayStrip(runs, today, 14);
  assert.equal(cells.length, 14);
  assert.equal(cells[13].outcome, "partial");
  assert.equal(cells[11].outcome, "failed");
  assert.equal(cells[12].outcome, null);
});

test("the strip runs oldest first and ends on today's local date", () => {
  const cells = dayStrip([], new Date("2026-11-02T00:30:00"), 14);
  assert.equal(cells[0].day, "2026-10-20");
  assert.equal(cells[13].day, "2026-11-02");
  assert.ok(cells.every((c) => c.outcome === null));
});

test("a run older than the strip, or after today, is left out", () => {
  const today = new Date("2026-10-20T12:00:00");
  const cells = dayStrip(
    [
      { finished_at: "2026-10-06T23:00:00", outcome: "failed" },
      { finished_at: "2026-10-21T01:00:00", outcome: "failed" },
    ],
    today,
    14,
  );
  assert.ok(cells.every((c) => c.outcome === null));
});

test("the sentence counts days with a report and names what was not done", () => {
  const today = new Date("2026-10-20T12:00:00");
  const run = (day: string, outcome: "ok" | "partial" | "failed") => ({ finished_at: `2026-10-${day}T09:00:00`, outcome });
  assert.equal(dayStripLabel(dayStrip([], today, 14)), "Last 14 days: no reports");
  assert.equal(dayStripLabel(dayStrip([run("20", "ok")], today, 14)), "Last 14 days: a report on 1 day, all done");
  assert.equal(
    dayStripLabel(dayStrip([run("20", "ok"), run("19", "partial"), run("18", "failed"), run("17", "ok")], today, 14)),
    "Last 14 days: a report on 4 days, 1 failed, 1 partly done",
  );
});

test("an automation is reporting while a run sits in the strip, and the strip is 14 days", () => {
  const today = new Date("2026-10-20T12:00:00");
  assert.equal(STRIP_DAYS, 14);
  assert.equal(reportedInStrip([], today), false);
  assert.equal(reportedInStrip([{ finished_at: "2026-10-07T09:00:00", outcome: "failed" }], today), true);
  // The day before the strip's first day is out, like the strip itself.
  assert.equal(reportedInStrip([{ finished_at: "2026-10-06T23:00:00", outcome: "ok" }], today), false);
});
