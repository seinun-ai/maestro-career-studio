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

/** automation → when its newest run finished (the list comes newest first). */
export function latestByAutomation(runs: readonly { automation: string; finished_at: string }[]) {
  const map = new Map<string, string>();
  for (const run of runs) if (!map.has(run.automation)) map.set(run.automation, run.finished_at);
  return map;
}

/** An Automations card's line. `undefined` while unknown (loading or failed): no line. */
export function lastRanLine(finishedAt: string | null | undefined, ago: (iso: string) => string): string | null {
  if (finishedAt === undefined) return null;
  return finishedAt === null ? "Not run yet" : `Last ran ${ago(finishedAt)}`;
}

export const AGENT_RUNS_LATEST_KEY = ["agent-runs", "latest"] as const;
