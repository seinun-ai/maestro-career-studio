import assert from "node:assert/strict";
import { test } from "node:test";

import {
  countWords,
  dayHeading,
  moreStepLabel,
  moreSummary,
  nextUpAction,
  STEP_WORDS,
  todayKey,
  todayPath,
  weekBars,
  weekLabel,
  weekLine,
} from "./today.ts";

test("the read sends the zone name and the offset, east positive", () => {
  assert.equal(
    todayPath({ tz: "Europe/Berlin", offsetMinutes: 120 }),
    "/api/today?tz=Europe%2FBerlin&utc_offset_minutes=120",
  );
  assert.equal(todayPath({ tz: "America/New_York", offsetMinutes: -240 }), "/api/today?tz=America%2FNew_York&utc_offset_minutes=-240");
  // No zone name (a browser that reports none): the offset alone, which the server reads.
  assert.equal(todayPath({ tz: null, offsetMinutes: 330 }), "/api/today?utc_offset_minutes=330");
  assert.deepEqual(todayKey({ tz: "Asia/Kolkata", offsetMinutes: 330 }), ["today", "Asia/Kolkata", 330]);
});

test("next up's one button says the move and goes where it is made", () => {
  assert.deepEqual(nextUpAction({ kind: "pdf_ready", job_id: "j1", status: "draft" }), {
    label: "Apply",
    href: "/jobs/j1?tab=qa",
  });
  assert.deepEqual(nextUpAction({ kind: "offer", job_id: "j2", status: "offered" }), {
    label: "Review the offer",
    href: "/jobs/j2?tab=qa",
  });
  // A proposal opens its job from the Agent inbox, on the agent's card.
  assert.deepEqual(nextUpAction({ kind: "needs_you", job_id: "j3", status: "needs_decision" }), {
    label: "Answer",
    href: "/jobs/j3?from=proposals",
  });
  assert.deepEqual(nextUpAction({ kind: "needs_you", job_id: "j4", status: "needs_human" }), {
    label: "See what it needs",
    href: "/jobs/j4?from=proposals",
  });
});

test("every step the server dates has a word", () => {
  for (const key of ["saved", "gaps_closed", "tailored", "applied", "interviewing", "offered", "proposed"] as const) {
    assert.ok(STEP_WORDS[key], key);
  }
  assert.equal(STEP_WORDS.offered, "Offer");
});

test("a count's words agree with the count", () => {
  assert.equal(countWords({ key: "to_approve", count: 1, href: "/proposals" }), "Agent job to review");
  assert.equal(countWords({ key: "to_approve", count: 3, href: "/proposals" }), "Agent jobs to review");
  assert.equal(countWords({ key: "to_check", count: 1, href: "/x" }), "Tailored resume to check");
  assert.equal(countWords({ key: "to_check", count: 4, href: "/x" }), "Tailored resumes to check");
  assert.equal(countWords({ key: "quiet", count: 5, days: 14, href: "/x" }), "No reply after 14 days");
  assert.equal(countWords({ key: "gaps_to_close", count: 1, gaps: 2, href: "/x" }), "Job with gaps to close");
  assert.equal(countWords({ key: "gaps_to_close", count: 3, gaps: 7, href: "/x" }), "Jobs with gaps to close");
  assert.equal(countWords({ key: "health_check", count: 1, href: "/x" }), "Base resume needs a health check");
  assert.equal(countWords({ key: "health_check", count: 2, href: "/x" }), "Base resumes need a health check");
});

test("the fold says what it holds without opening", () => {
  assert.equal(
    moreSummary([
      { key: "gaps_to_close", count: 3, gaps: 7, href: "/a" },
      { key: "health_check", count: 1, href: "/b" },
    ]),
    "7 gaps to close, 1 health check",
  );
  assert.equal(
    moreSummary([
      { key: "gaps_to_close", count: 1, gaps: 1, href: "/a" },
      { key: "health_check", count: 2, href: "/b" },
    ]),
    "1 gap to close, 2 health checks",
  );
  // No unanswered gap reported: the jobs are counted instead, never a made-up gap count.
  assert.equal(moreSummary([{ key: "gaps_to_close", count: 2, href: "/a" }]), "2 jobs with gaps");
});

test("a folded row's link names where it goes", () => {
  assert.equal(moreStepLabel({ key: "gaps_to_close", count: 3, gaps: 7, href: "/applications?stage=gaps" }), "See jobs");
  assert.equal(moreStepLabel({ key: "health_check", count: 1, href: "/base-resumes/x/health" }), "Check health");
  assert.equal(moreStepLabel({ key: "health_check", count: 2, href: "/base-resumes" }), "See base resumes");
});

const WEEK = [
  { date: "2026-10-14", applied: 2 },
  { date: "2026-10-15", applied: 3 },
  { date: "2026-10-16", applied: 1 },
  { date: "2026-10-17", applied: 0 },
  { date: "2026-10-18", applied: 0 },
  { date: "2026-10-19", applied: 1 },
  { date: "2026-10-20", applied: 2 },
];

test("the week's bars: local weekdays, today last, heights against the busiest day", () => {
  const bars = weekBars(WEEK);
  assert.deepEqual(bars.map((b) => b.day), ["Wed", "Thu", "Fri", "Sat", "Sun", "Mon", "Today"]);
  assert.deepEqual(bars.map((b) => b.pct), [67, 100, 33, 0, 0, 33, 67]);
  assert.deepEqual(bars.map((b) => b.today), [false, false, false, false, false, false, true]);
  assert.equal(
    weekLabel(bars),
    "Applied per day: Wed 2, Thu 3, Fri 1, Sat 0, Sun 0, Mon 1, today 2",
  );
  // A week with nothing sent draws no bar taller than the empty stub.
  assert.deepEqual(weekBars(WEEK.map((d) => ({ ...d, applied: 0 }))).map((b) => b.pct), [0, 0, 0, 0, 0, 0, 0]);
});

test("the week in words", () => {
  assert.equal(weekLine({ applied: 9, applied_all_time: 64 }), "applied, 64 in all");
  // Every application went out this week: "in all" would repeat the number.
  assert.equal(weekLine({ applied: 3, applied_all_time: 3 }), "applied");
  assert.equal(weekLine({ applied: 0, applied_all_time: 0 }), "applied");
});

test("the header's day is the server's local date, read as a calendar day", () => {
  assert.equal(dayHeading("2026-10-20"), "Tue, Oct 20");
  assert.equal(dayHeading("not a date"), "");
});
