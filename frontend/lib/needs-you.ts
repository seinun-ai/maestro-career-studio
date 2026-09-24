// Which statuses need the user is the Needs you lane's list, `NEEDS_YOU_STATUSES` in lib/inbox-lanes.ts.
// Pure (lib/needs-you.test.ts); pinned by test_frontend_agent_inbox.py.

export type NavBadge = { text: string; spoken: string };

/** The sidebar badge for a count. Hidden (null) at 0, and while the count is
 *  unknown (loading, failed, or the server-rendered fallback), so it never
 *  claims a number it does not have. "99+" past 99. `spoken` completes the
 *  link's accessible name: "Agent inbox, 3 need you". */
export function needsYouBadge(count: number | null | undefined): NavBadge | null {
  if (count == null || !Number.isFinite(count) || count < 1) return null;
  const n = Math.floor(count);
  return {
    text: n > 99 ? "99+" : String(n),
    spoken: `${n} ${n === 1 ? "needs" : "need"} you`,
  };
}
