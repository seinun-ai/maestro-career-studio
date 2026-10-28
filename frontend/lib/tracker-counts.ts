/**
 * Which rows a Status value shows, and the Jobs list's chip counts. No imports: `node --test` loads this file
 * as it is.
 */

// The Status keys each group value stands for. Closed is the server's closed stage (rejected, withdrawn, skipped)
// and the agent jobs you skipped: either way you are not pursuing them. An accepted offer stays active.
const CLOSED_KEYS = ["rejected", "withdrawn", "skipped", "agent_skipped"];
const INTERVIEW_KEYS = ["interviewing", "offered"];

/** Whether a row with this Status key shows under a Status value: `all`, a group (`active`, `interviews`,
 *  `closed`) or one key. */
export function matchesFilter(filter: string, key: string): boolean {
  if (filter === "all") return true;
  if (filter === "active") return !CLOSED_KEYS.includes(key);
  if (filter === "interviews") return INTERVIEW_KEYS.includes(key);
  if (filter === "closed") return CLOSED_KEYS.includes(key);
  return key === filter;
}

/** A row as the strip counts it: its Status filter key and its stage (undefined from a backend without one). */
export type CountRow = { filterKey: string; stage?: string };
export type StripAxes = { filter: string; stage: string | null };

/**
 * How many rows a chip shows once pressed: its own axis set to its value, the other axis as it is now, since
 * the stage ANDs with the Status filter. A stage option passes `{ stage }`; a list chip, a preset of both,
 * passes the preset as `current` and `{}`.
 */
export function chipCount(rows: readonly CountRow[], current: StripAxes, chip: Partial<StripAxes>): number {
  const filter = chip.filter ?? current.filter;
  const stage = chip.stage !== undefined ? chip.stage : current.stage;
  return rows.filter((r) => matchesFilter(filter, r.filterKey) && (!stage || r.stage === stage)).length;
}
