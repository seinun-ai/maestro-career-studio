// The Automations card's day strip: what the runs reported, one cell per day (backend agent_runs).
// Pure: `node --test` loads it.

import type { RunOutcome } from "./agent-runs";

export type DayCell = { day: string; outcome: RunOutcome | null };

/** How many days a strip shows: the Automations cards' window. */
export const STRIP_DAYS = 14;

const SEVERITY: Record<RunOutcome, number> = { ok: 1, partial: 2, failed: 3 };

/** "2026-10-20" for the local calendar day `date` falls on. */
function localDay(date: Date): string {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

/** One cell per local calendar day, oldest first, ending on `today`. A day takes its worst outcome
 * (failed, then partial, then ok); a day with no report is `null`. Local, not UTC, so a run at
 * 23:30 counts on the evening it ran. Runs outside the strip are left out. */
export function dayStrip(
  runs: readonly { finished_at: string; outcome: RunOutcome }[],
  today: Date,
  days: number,
): DayCell[] {
  const worst = new Map<string, RunOutcome>();
  for (const run of runs) {
    const at = new Date(run.finished_at);
    if (Number.isNaN(at.getTime()) || !(run.outcome in SEVERITY)) continue;
    const day = localDay(at);
    const seen = worst.get(day);
    if (!seen || SEVERITY[run.outcome] > SEVERITY[seen]) worst.set(day, run.outcome);
  }
  return Array.from({ length: days }, (_, i) => {
    // Calendar arithmetic in local time, so a daylight-saving change never skips or repeats a day.
    const day = localDay(new Date(today.getFullYear(), today.getMonth(), today.getDate() - (days - 1 - i)));
    return { day, outcome: worst.get(day) ?? null };
  });
}

/** The strip in one sentence: "Last 14 days: a report on 4 days, 1 failed, 1 partly done". */
export function dayStripLabel(cells: readonly DayCell[]): string {
  const head = `Last ${cells.length} days`;
  const reported = cells.filter((c) => c.outcome !== null);
  if (reported.length === 0) return `${head}: no reports`;
  const on = `a report on ${reported.length} ${reported.length === 1 ? "day" : "days"}`;
  const failed = reported.filter((c) => c.outcome === "failed").length;
  const partly = reported.filter((c) => c.outcome === "partial").length;
  if (failed === 0 && partly === 0) return `${head}: ${on}, all done`;
  const notDone = [failed ? `${failed} failed` : "", partly ? `${partly} partly done` : ""].filter(Boolean);
  return `${head}: ${on}, ${notDone.join(", ")}`;
}

/** Whether any run falls inside the strip ending on `today`: what puts an automation under Reporting. */
export function reportedInStrip(
  runs: readonly { finished_at: string; outcome: RunOutcome }[],
  today: Date,
  days: number = STRIP_DAYS,
): boolean {
  return dayStrip(runs, today, days).some((c) => c.outcome !== null);
}
