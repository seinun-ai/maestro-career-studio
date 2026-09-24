/**
 * How many of a gap analysis's gaps are answered, skipped and still open: the gap page's footer, each
 * category's badge and the Score and tailor tab's "Continue gap analysis" read these, so the three agree.
 *
 * Only the gaps listed count, so a stored resolution for a gap the analysis no longer lists inflates
 * nothing. `cannot_confirm` is a skip for the resume (its career-history record is kept elsewhere), so
 * it counts as skipped, never answered. No imports: `node --test` loads this file as it is.
 */
export type GapCounts = { answered: number; skipped: number; open: number; total: number };

export function gapCounts(
  gapIds: readonly string[],
  resolutions: readonly { gap_id: string; action: string }[],
): GapCounts {
  const byGap = new Map(resolutions.map((r) => [r.gap_id, r] as const));
  let answered = 0;
  let skipped = 0;
  let open = 0;
  for (const id of gapIds) {
    const resolution = byGap.get(id);
    if (!resolution) open += 1;
    else if (resolution.action === "skip" || resolution.action === "cannot_confirm") skipped += 1;
    else answered += 1;
  }
  return { answered, skipped, open, total: gapIds.length };
}
