/** Roles a multi-role line chart draws. Two lines per role (base dashed, tailored
 *  solid): 4 roles = 8 lines and 4 of CHART_COLORS' 6 hues, so colours never cycle. */
export const MAX_ROLE_SERIES = 4;

/** Rank series keys (roles, resumes) by total weight, key asc on ties; split
 *  into the drawn head and the hidden tail, so a chart never cycles colours. */
export function splitTopSeries<T>(
  rows: T[],
  keyOf: (row: T) => string,
  weightOf: (row: T) => number,
  max = MAX_ROLE_SERIES,
): { shown: string[]; hidden: string[] } {
  const totals = new Map<string, number>();
  for (const row of rows) {
    const key = keyOf(row);
    totals.set(key, (totals.get(key) ?? 0) + weightOf(row));
  }
  const ranked = [...totals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key]) => key);
  return { shown: ranked.slice(0, max), hidden: ranked.slice(max) };
}
