/**
 * Today's words and shapes (`GET /api/today`, backend/app/services/today.py), pure so `node --test` loads it:
 * it imports only types, which the loader erases. The server picks what matters and counts it; this file
 * only says it.
 */
import type { TodayCount, TodayNextUp, TodayResponse, TodayStep } from "./types";

/** The browser's time zone as the server reads it: the IANA name (null when the browser gives none) and
 * the offset from UTC in minutes, east positive. Both go: a Windows install may have no zone database. */
export type BrowserZone = { tz: string | null; offsetMinutes: number };

export function todayPath(zone: BrowserZone): string {
  const params = new URLSearchParams();
  if (zone.tz) params.set("tz", zone.tz);
  params.set("utc_offset_minutes", String(zone.offsetMinutes));
  return `/api/today?${params}`;
}

/** Keyed by the zone: a laptop that travels reads its new local days. */
export function todayKey(zone: BrowserZone) {
  return ["today", zone.tz, zone.offsetMinutes] as const;
}

export type NextUpAction = { label: string; href: string };

/**
 * Next up's one button: the move, and the place it is made. A ready PDF and an offer open the job's Apply
 * step (where an application is sent and its status kept); a proposal opens its job from the Agent inbox,
 * on the agent's card, where a question is answered.
 */
export function nextUpAction(item: Pick<TodayNextUp, "kind" | "job_id" | "status">): NextUpAction {
  switch (item.kind) {
    case "offer":
      return { label: "Review the offer", href: `/jobs/${item.job_id}?tab=qa` };
    case "needs_you":
      return {
        label: item.status === "needs_human" ? "See what it needs" : "Answer",
        href: `/jobs/${item.job_id}?from=proposals`,
      };
    default:
      return { label: "Apply", href: `/jobs/${item.job_id}?tab=qa` };
  }
}

/** "Where this job is": each step the server dates. "Offer" is the status chip's word. */
export const STEP_WORDS: Readonly<Record<TodayStep["key"], string>> = {
  saved: "Saved",
  gaps_closed: "Gaps closed",
  tailored: "Tailored",
  applied: "Applied",
  interviewing: "Interviewing",
  offered: "Offer",
  proposed: "Proposed",
};

/** What a count counts, agreeing with it: "Agent job to review", "Agent jobs to review". */
export function countWords(count: TodayCount): string {
  const one = count.count === 1;
  switch (count.key) {
    case "to_approve":
      return one ? "Agent job to review" : "Agent jobs to review";
    case "to_check":
      return one ? "Tailored resume to check" : "Tailored resumes to check";
    case "quiet":
      return `No reply after ${count.days ?? 14} days`;
    case "gaps_to_close":
      return one ? "Job with gaps to close" : "Jobs with gaps to close";
    case "health_check":
      return one ? "Base resume needs a health check" : "Base resumes need a health check";
  }
}

/** Where a count's people are when the list its link opens holds more than the count, else null. The Jobs
 * list has no "no reply" filter, so the quiet card opens every job waiting to hear and says the quiet ones
 * are among them, rather than promising a list of only those. */
export function countWhere(count: TodayCount): string | null {
  return count.key === "quiet" ? "Among your jobs waiting to hear" : null;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The fold's summary, so the row says what it holds without opening: "7 gaps to close, 1 health check". */
export function moreSummary(more: readonly TodayCount[]): string {
  return more
    .map((count) => {
      if (count.key === "gaps_to_close") {
        return count.gaps ? plural(count.gaps, "gap to close", "gaps to close") : plural(count.count, "job with gaps", "jobs with gaps");
      }
      if (count.key === "health_check") return plural(count.count, "health check", "health checks");
      return `${count.count} ${countWords(count).toLowerCase()}`;
    })
    .join(", ");
}

/** A folded row's next step (D3's blue link): where its `href` goes, in words. One base resume opens its
 * own health report; several open the gallery. */
export function moreStepLabel(count: TodayCount): string {
  if (count.key === "health_check") return count.count === 1 ? "Check health" : "See base resumes";
  return "See jobs";
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** An ISO day as a local calendar day: `new Date("2026-10-20")` is UTC midnight, the 19th west of Greenwich. */
function calendarDay(iso: string): Date | null {
  const m = ISO_DAY.exec(iso);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

/** The header's day, from the server's local date: "Tue, Oct 20"; "" when unreadable. */
export function dayHeading(iso: string): string {
  const day = calendarDay(iso);
  return day ? day.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) : "";
}

export type WeekBar = { date: string; applied: number; day: string; pct: number; today: boolean };

/** Seven bars, oldest first, the last one today; each as a share of the busiest day (0 draws the stub). */
export function weekBars(days: TodayResponse["week"]["days"]): WeekBar[] {
  const most = Math.max(0, ...days.map((d) => d.applied));
  return days.map((d, i) => {
    const today = i === days.length - 1;
    const date = calendarDay(d.date);
    return {
      date: d.date,
      applied: d.applied,
      day: today ? "Today" : date ? date.toLocaleDateString("en-US", { weekday: "short" }) : d.date,
      pct: most > 0 ? Math.round((d.applied / most) * 100) : 0,
      today,
    };
  });
}

/** The chart as one sentence for a screen reader: "Applied per day: Wed 2, …, today 2". */
export function weekLabel(bars: readonly WeekBar[]): string {
  return `Applied per day: ${bars.map((b) => `${b.today ? "today" : b.day} ${b.applied}`).join(", ")}`;
}

/** Under this week's number: "applied, 64 in all", or just "applied" when every one went out this week. */
export function weekLine(week: Pick<TodayResponse["week"], "applied" | "applied_all_time">): string {
  return week.applied_all_time > week.applied ? `applied, ${week.applied_all_time} in all` : "applied";
}
