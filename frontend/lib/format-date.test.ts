import assert from "node:assert/strict";
import { test } from "node:test";

import { formatShortDate, formatWeekOf } from "./format-date.ts";

const NOW = new Date(2026, 8, 24, 12);

test("a day this year reads as month and day", () => {
  assert.equal(formatShortDate("2026-09-14", NOW), "Sep 14");
  assert.equal(formatShortDate(new Date(2026, 6, 1, 23, 59), NOW), "Jul 1");
});

test("a day in another year keeps its year", () => {
  assert.equal(formatShortDate("2025-12-31", NOW), "Dec 31, 2025");
});

test("a date-only value is a calendar day, never shifted by the time zone", () => {
  assert.equal(formatShortDate("2026-01-01", NOW), "Jan 1");
});

test("a timestamp reads as its local day", () => {
  const local = new Date(2026, 2, 5, 9, 30);
  assert.equal(formatShortDate(local.toISOString(), NOW), "Mar 5");
});

test("an unreadable value is empty, never Invalid Date", () => {
  assert.equal(formatShortDate("not a date", NOW), "");
});

test("a weekly point reads as the week it starts", () => {
  assert.equal(formatWeekOf("2026-09-21"), "Week of Sep 21");
  assert.equal(formatWeekOf("not a date"), "");
});
