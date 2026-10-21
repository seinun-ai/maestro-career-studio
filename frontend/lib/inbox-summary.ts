// The Agent inbox header's counts (`GET /api/proposals/summary`): what waits for review, what is queued, and what
// went out this week. Pure, so `node --test` loads it (no imports).

type SummaryCounts = { to_review: number; queued: number; applied_this_week: number };

export type InboxCount = { key: keyof SummaryCounts; value: number; label: string; anchor: string };

/**
 * The three counts, in order, zeros kept: the header holds its shape, and a zero is a true answer. "Applied this
 * week" is the server's rolling seven days of applications an agent sent or you made yourself; each count jumps
 * to the lane that holds it (History for the applied ones).
 */
export function inboxCounts(counts: SummaryCounts): InboxCount[] {
  return [
    { key: "to_review", value: counts.to_review, label: "to review", anchor: "inbox-to-review" },
    { key: "queued", value: counts.queued, label: "queued", anchor: "inbox-queued" },
    { key: "applied_this_week", value: counts.applied_this_week, label: "applied this week", anchor: "inbox-history" },
  ];
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
