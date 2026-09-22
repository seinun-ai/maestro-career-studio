/** Roles a multi-role line chart draws. Two lines per role (base dashed, tailored
 *  solid): 4 roles = 8 lines and 4 of CHART_COLORS' 6 hues, so colours never cycle. */
export const MAX_ROLE_SERIES = 4;

/** Rank roles by total weight, key asc on ties; split into drawn and hidden. */
export function splitTopRoles<T>(
  rows: T[],
  roleOf: (row: T) => string,
  weightOf: (row: T) => number,
  max = MAX_ROLE_SERIES,
): { shown: string[]; hidden: string[] } {
  const totals = new Map<string, number>();
  for (const row of rows) {
    const role = roleOf(row);
    totals.set(role, (totals.get(role) ?? 0) + weightOf(row));
  }
  const ranked = [...totals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([role]) => role);
  return { shown: ranked.slice(0, max), hidden: ranked.slice(max) };
}
