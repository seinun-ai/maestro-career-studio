// The Agent inbox's one summary line (`GET /api/proposals/summary`): what needs you, what is queued, what
// went out this week, and what is new. Pure, so `node --test` loads it (no imports).

type SummaryCounts = { new: number; queued: number; needs_you: number; applied_this_week: number };

export type SummaryPart = { key: keyof SummaryCounts; text: string; anchor: string };

/** The parts of the line, in order; a zero count is left out, so nothing waiting is an empty list. */
export function summaryParts(counts: SummaryCounts): SummaryPart[] {
  const parts: SummaryPart[] = [];
  if (counts.new > 0) parts.push({ key: "new", text: `${counts.new} new`, anchor: "inbox-to-review" });
  if (counts.needs_you > 0) {
    parts.push({
      key: "needs_you",
      text: `${counts.needs_you} ${counts.needs_you === 1 ? "needs" : "need"} you`,
      anchor: "inbox-needs-you",
    });
  }
  if (counts.queued > 0) parts.push({ key: "queued", text: `${counts.queued} queued`, anchor: "inbox-queued" });
  if (counts.applied_this_week > 0) {
    parts.push({ key: "applied_this_week", text: `${counts.applied_this_week} applied this week`, anchor: "inbox-history" });
  }
  return parts;
}

/** The share of the daily limit from which the cap meter is worth showing. */
const CAP_SHOWN_FROM = 0.8;

/**
 * Whether the "Applications per day" meter shows: only at 80 percent of the limit or more. Below that it is
 * not news. A limit of none (0) is always news: nothing can be applied to.
 */
export function capNearLimit(used: number, max: number): boolean {
  return max <= 0 || used / max >= CAP_SHOWN_FROM;
}
