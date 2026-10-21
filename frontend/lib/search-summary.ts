/**
 * Analytics' search summary (`GET /api/explore/search-summary`, backend/app/services/search_summary.py). Pure so
 * `node --test` loads it: it imports only types. The server counts everything; this file asks for a period and
 * a source and lays the answer out.
 */
import type { RateCount, SearchSummary } from "./types";

/** The period control, in its order. "all" is every week since the first application sent. */
export const PERIODS = [
  { value: "4", label: "4 weeks" },
  { value: "12", label: "12 weeks" },
  { value: "all", label: "All" },
] as const;
export type Period = (typeof PERIODS)[number]["value"];
export const DEFAULT_PERIOD: Period = "12";

/** `services/search_summary.py` QUIET_AFTER_DAYS and MIN_REPLIES_FOR_TIMING, for the definitions shown before the
 * summary loads (the summary itself carries both). */
export const QUIET_AFTER_DAYS = 30;
export const MIN_REPLIES_FOR_TIMING = 5;

/** The source toggle's values (`components/source-toggle.tsx` SOURCES). */
export type SummarySource = SearchSummary["source"];

/** Every request names its period and its source, All included: the page never leans on the server's defaults. */
export function summaryPath(period: Period, source: SummarySource): string {
  return `/api/explore/search-summary?${new URLSearchParams({ weeks: period, source })}`;
}

export function summaryKey(period: Period, source: SummarySource) {
  return ["explore", "search-summary", period, source] as const;
}

/** "in 12 weeks"; null for All, whose start the caller dates. */
export function windowWords(weeks: number | null): string | null {
  if (weeks === null) return null;
  return `in ${weeks} ${weeks === 1 ? "week" : "weeks"}`;
}

export interface FunnelRow {
  key: "applied" | "heard_back" | "interview" | "offer";
  label: string;
  count: number;
  /** Of the row above; null on Applied, the top. */
  rate: RateCount | null;
  /** The row above's noun, for "5 of 12 replies". */
  unit: readonly [string, string] | null;
  /** The bar: this row's count as a share of Applied, 0 to 100. */
  share: number;
}

/** Applied, then heard back of applied, interview of heard back, offer of interview: each bar on Applied's scale. */
export function funnelRows(s: SearchSummary): FunnelRow[] {
  const share = (n: number) => (s.applied > 0 ? (n / s.applied) * 100 : 0);
  return [
    { key: "applied", label: "Applied", count: s.applied, rate: null, unit: null, share: share(s.applied) },
    {
      key: "heard_back",
      label: "Heard back",
      count: s.heard_back.count,
      rate: s.heard_back,
      unit: ["application", "applications"],
      share: share(s.heard_back.count),
    },
    {
      key: "interview",
      label: "Interview",
      count: s.interview.count,
      rate: s.interview,
      unit: ["reply", "replies"],
      share: share(s.interview.count),
    },
    {
      key: "offer",
      label: "Offer",
      count: s.offer.count,
      rate: s.offer,
      unit: ["interview", "interviews"],
      share: share(s.offer.count),
    },
  ];
}

/** Where the middle half (25th to 75th percentile) and the median sit on a track from 0 to at least the quiet
 * window's 30 days, in percent of its length; null while the server sends no days (fewer than 5 dated replies). */
export function timingTrack(
  t: SearchSummary["time_to_hear_back"],
): { from: number; width: number; median: number } | null {
  if (t.median_days === null || t.p25_days === null || t.p75_days === null) return null;
  const scale = Math.max(QUIET_AFTER_DAYS, t.p75_days);
  const at = (days: number) => Math.round((days / scale) * 1000) / 10;
  return { from: at(t.p25_days), width: at(t.p75_days - t.p25_days), median: at(t.median_days) };
}
