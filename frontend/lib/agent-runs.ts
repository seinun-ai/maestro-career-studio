// The run log's words (backend services/agent_runs.py). Pure: `node --test` loads it.

export type RunOutcome = "ok" | "partial" | "failed";

const COUNT_ORDER = ["found", "proposed", "tailored", "updated", "skipped", "needs_you"] as const;

function countWords(key: (typeof COUNT_ORDER)[number], n: number): string {
  if (key === "needs_you") return `${n} ${n === 1 ? "needs" : "need"} you`;
  return `${n} ${key}`;
}

/** "12 found, 4 proposed, 8 skipped": the number first, a fixed order, zeros left out. */
export function countsLine(counts: Record<string, number>): string {
  const parts = COUNT_ORDER.filter((k) => (counts[k] ?? 0) > 0).map((k) => countWords(k, counts[k]));
  return parts.length === 0 ? "Nothing to report" : parts.join(", ");
}

/**
 * A Reporting card's line about its newest run: "2 hours ago · 12 found, 4 proposed · by Claude on your bot".
 * All-zero counts say nothing. `who` is the agent's display name (lib/agent-name.ts; this file imports
 * nothing), null when unknown; `on_bot` is absent from an older backend.
 */
export function reportLine(
  run: { finished_at: string; counts: Record<string, number>; on_bot?: boolean },
  who: string | null,
  ago: (iso: string) => string,
): string {
  const parts = [ago(run.finished_at)];
  if (COUNT_ORDER.some((k) => (run.counts[k] ?? 0) > 0)) parts.push(countsLine(run.counts));
  const where = run.on_bot ? "on your bot" : "";
  if (who) parts.push(where ? `by ${who} ${where}` : `by ${who}`);
  else if (where) parts.push(where);
  return parts.join(" · ");
}

const OUTCOME_WORDS: Record<RunOutcome, string> = { ok: "Done", partial: "Partly done", failed: "Failed" };

export function outcomeWord(outcome: RunOutcome): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

/** automation → its runs, newest first like the list they come from. */
export function runsByAutomation<T extends { automation: string }>(runs: readonly T[]): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const run of runs) {
    const list = map.get(run.automation);
    if (list) list.push(run);
    else map.set(run.automation, [run]);
  }
  return map;
}

/** The Recent runs row's summary: how many runs it lists (the newest per automation), then the ones that did
 * not finish: "3 · 1 failed, 1 partly done". Null when it lists none. */
export function recentRunsSummary(latest: readonly { outcome: RunOutcome }[]): string | null {
  if (latest.length === 0) return null;
  const failed = latest.filter((r) => r.outcome === "failed").length;
  const partly = latest.filter((r) => r.outcome === "partial").length;
  const notDone = [failed ? `${failed} failed` : "", partly ? `${partly} partly done` : ""].filter(Boolean);
  return notDone.length ? `${latest.length} · ${notDone.join(", ")}` : String(latest.length);
}

export const AGENT_RUNS_LATEST_KEY = ["agent-runs", "latest"] as const;

/** Every retained run, newest first: the log keeps 200 (backend services/agent_runs.py), the list's top limit. */
export const AGENT_RUNS_PATH = "/api/agent-runs?limit=200";
export const AGENT_RUNS_KEY = ["agent-runs", "all"] as const;

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
