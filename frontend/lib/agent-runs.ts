// The run log's words (backend services/agent_runs.py). Pure: `node --test` loads it.

export type RunOutcome = "ok" | "partial" | "failed";

const COUNT_ORDER = ["found", "proposed", "tailored", "updated", "skipped", "needs_you"] as const;

function countWords(key: (typeof COUNT_ORDER)[number], n: number): string {
  if (key === "needs_you") return `${n} ${n === 1 ? "needs" : "need"} you`;
  return `${key} ${n}`;
}

/** "Found 12 · proposed 4 · skipped 8": fixed order, zeros left out, first word capitalized. */
export function countsLine(counts: Record<string, number>): string {
  const parts = COUNT_ORDER.filter((k) => (counts[k] ?? 0) > 0).map((k) => countWords(k, counts[k]));
  if (parts.length === 0) return "Nothing to report";
  const line = parts.join(" · ");
  return line[0].toUpperCase() + line.slice(1);
}

const OUTCOME_WORDS: Record<RunOutcome, string> = { ok: "Done", partial: "Partly done", failed: "Failed" };

export function outcomeWord(outcome: RunOutcome): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

/** automation → its newest run's finish time and outcome (the list comes newest first). */
export function latestByAutomation(
  runs: readonly { automation: string; finished_at: string; outcome: RunOutcome }[],
) {
  const map = new Map<string, { finished_at: string; outcome: RunOutcome }>();
  for (const run of runs) {
    if (!map.has(run.automation)) map.set(run.automation, { finished_at: run.finished_at, outcome: run.outcome });
  }
  return map;
}

/** An Automations card's line. `undefined` while unknown (loading or failed): no line. */
export function lastRanLine(finishedAt: string | null | undefined, ago: (iso: string) => string): string | null {
  if (finishedAt === undefined) return null;
  return finishedAt === null ? "Not run yet" : `Last ran ${ago(finishedAt)}`;
}

export const AGENT_RUNS_LATEST_KEY = ["agent-runs", "latest"] as const;

/** Where the inbox's "See runs" goes: the Recent runs list on the Automations page. */
export const RECENT_RUNS_HREF = "/automations#recent-runs";

/**
 * The Agent inbox's one line about runs: "Job hunt proposed 4 jobs 2 hours ago", only when the newest run
 * (the list comes newest first) proposed jobs, which is what puts them in the inbox. Every other run is on
 * the Automations page.
 */
export function proposedLine(
  runs: readonly { title: string; finished_at: string; counts: Record<string, number> }[],
  ago: (iso: string) => string,
): string | null {
  const newest = runs[0];
  const proposed = newest?.counts.proposed ?? 0;
  if (!newest || proposed <= 0) return null;
  return `${newest.title} proposed ${proposed} ${proposed === 1 ? "job" : "jobs"} ${ago(newest.finished_at)}`;
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * The refused requests worth showing now: answered since the last inbox visit (`since`), and never more than a
 * week ago, so an old refusal does not sit in the inbox for good. With no visit known the week is the window;
 * a request with no answer time is kept.
 */
export function recentRefusals<T extends { answered_at: string | null }>(
  requests: readonly T[],
  since: string | null,
  nowMs: number,
): T[] {
  const weekAgo = nowMs - WEEK_MS;
  const visit = since ? Date.parse(since) : Number.NaN;
  const floor = Number.isNaN(visit) ? weekAgo : Math.max(visit, weekAgo);
  return requests.filter((r) => r.answered_at == null || Date.parse(r.answered_at) >= floor);
}
