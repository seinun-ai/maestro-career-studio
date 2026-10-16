/**
 * The Jobs list's quick-filter counts. No imports: `node --test` loads this file as it is.
 */

/** A row as the strip counts it: its Status filter key and its stage (undefined from a backend without one). */
export type CountRow = { filterKey: string; stage?: string };
export type StripAxes = { filter: string; stage: string | null };

/**
 * How many rows a chip shows once pressed: its own axis set to its value, the other axis as it is now, since
 * the stage chips AND with the Status select. A stage chip passes `{ stage }`, Needs you `{ filter }`.
 */
export function chipCount(rows: readonly CountRow[], current: StripAxes, chip: Partial<StripAxes>): number {
  const filter = chip.filter ?? current.filter;
  const stage = chip.stage !== undefined ? chip.stage : current.stage;
  return rows.filter((r) => (filter === "all" || r.filterKey === filter) && (!stage || r.stage === stage)).length;
}
