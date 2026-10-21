import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_PERIOD,
  PERIODS,
  funnelRows,
  summaryKey,
  summaryPath,
  timingTrack,
  windowWords,
} from "./search-summary.ts";
import type { SearchSummary } from "./types.ts";

const rc = (count: number, of: number) => ({ count, of, rate: null, low: null, high: null });

const summary = (over: Partial<SearchSummary> = {}): SearchSummary => ({
  weeks: 12,
  window_start: "2026-08-03",
  source: "all",
  applied: 10,
  applied_per_week: 0.8,
  heard_back: rc(4, 10),
  interview: rc(2, 4),
  offer: rc(1, 2),
  time_to_hear_back: { replies: 4, median_days: null, p25_days: null, p75_days: null },
  quiet: { ...rc(3, 6), after_days: 30 },
  score_gain: { n: 0, median: null, median_base: null, median_tailored: null },
  by_resume: [],
  series: [],
  undated_replies: 0,
  min_rate_n: 20,
  min_replies_for_timing: 5,
  ...over,
});

test("the period control offers 4 weeks, 12 weeks and All, on 12 weeks", () => {
  assert.deepEqual(PERIODS.map((p) => p.label), ["4 weeks", "12 weeks", "All"]);
  assert.deepEqual(PERIODS.map((p) => p.value), ["4", "12", "all"]);
  assert.equal(DEFAULT_PERIOD, "12");
});

test("every request sends its weeks and its source, All included", () => {
  assert.equal(summaryPath("12", "all"), "/api/explore/search-summary?weeks=12&source=all");
  assert.equal(summaryPath("4", "user"), "/api/explore/search-summary?weeks=4&source=user");
  assert.equal(summaryPath("all", "agent"), "/api/explore/search-summary?weeks=all&source=agent");
});

test("the cache key names the period and the source, so each pair is its own entry", () => {
  assert.deepEqual(summaryKey("4", "agent"), ["explore", "search-summary", "4", "agent"]);
  assert.notDeepEqual(summaryKey("4", "all"), summaryKey("12", "all"));
});

test("the window in words: N weeks, or nothing for All (the caller names the start)", () => {
  assert.equal(windowWords(12), "in 12 weeks");
  assert.equal(windowWords(1), "in 1 week");
  assert.equal(windowWords(null), null);
});

test("the funnel nests: each row's bar is a share of Applied, and its count is of the row above", () => {
  const rows = funnelRows(summary());
  assert.deepEqual(rows.map((r) => r.label), ["Applied", "Heard back", "Interview", "Offer"]);
  assert.deepEqual(rows.map((r) => r.count), [10, 4, 2, 1]);
  assert.deepEqual(rows.map((r) => r.share), [100, 40, 20, 10]);
  assert.equal(rows[0].rate, null);
  assert.deepEqual(rows[2].rate, rc(2, 4));
  assert.deepEqual(rows.map((r) => r.unit), [null, ["application", "applications"], ["reply", "replies"], ["interview", "interviews"]]);
});

test("with nothing applied, no bar has a share", () => {
  const rows = funnelRows(summary({ applied: 0, heard_back: rc(0, 0), interview: rc(0, 0), offer: rc(0, 0) }));
  assert.deepEqual(rows.map((r) => r.share), [0, 0, 0, 0]);
});

test("time to hear back draws the middle half and the median on a track of at least 30 days", () => {
  assert.equal(timingTrack({ replies: 3, median_days: null, p25_days: null, p75_days: null }), null);
  assert.deepEqual(timingTrack({ replies: 12, median_days: 9, p25_days: 6, p75_days: 15 }), {
    from: 20,
    width: 30,
    median: 30,
  });
  // A slow search stretches the track to its 75th percentile.
  assert.deepEqual(timingTrack({ replies: 8, median_days: 30, p25_days: 20, p75_days: 40 }), {
    from: 50,
    width: 50,
    median: 75,
  });
});
