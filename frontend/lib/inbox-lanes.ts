import type { ProposalStatus } from "./types";

/**
 * The Agent inbox's lanes and the statuses each one holds (planner decision 20: Needs you · To review ·
 * Queued · Applying · History). Every status of `PROPOSAL_STATUSES` in `lib/types.ts` sits in exactly one
 * lane: `lib/inbox-lanes.test.ts` checks it at run time, and test_frontend_agent_inbox.py pins the table
 * against the types and the backend. Pure, so `node --test` loads it.
 */
export type InboxLane = "needs_you" | "triage" | "queued" | "in_flight" | "history";

export const INBOX_LANES: Readonly<Record<InboxLane, readonly ProposalStatus[]>> = {
  needs_you: ["needs_decision", "needs_human"],
  triage: ["pending_review"],
  queued: ["accepted"],
  in_flight: ["approved"],
  history: ["submitted", "submission_uncertain", "rejected", "expired"],
};

/** What waits on the user: the Needs you lane AND the sidebar's count, so the two never disagree. */
export const NEEDS_YOU_STATUSES = INBOX_LANES.needs_you;

/** Every status, lane by lane: the order of the status chips (the History filter, `STATUS_LABELS`). */
export const STATUS_ORDER: readonly ProposalStatus[] = (Object.keys(INBOX_LANES) as InboxLane[]).flatMap(
  (lane) => INBOX_LANES[lane],
);

/** The lane a status belongs to; null for a status this build does not know (a newer backend). */
export function laneOf(status: string): InboxLane | null {
  for (const lane of Object.keys(INBOX_LANES) as InboxLane[]) {
    if ((INBOX_LANES[lane] as readonly string[]).includes(status)) return lane;
  }
  return null;
}

/** The items of one lane, in their order. */
export function inLane<T extends { status: string }>(items: readonly T[], lane: InboxLane): T[] {
  return items.filter((item) => laneOf(item.status) === lane);
}

/**
 * The selected ids among `shown`, in its order. Bulk actions and the bar's count use only these: a row a
 * filter or the search hides, or one that has left the lane, is never acted on unseen.
 */
export function selectedAmong(shown: readonly { id: string }[], selected: ReadonlySet<string>): string[] {
  return shown.filter((item) => selected.has(item.id)).map((item) => item.id);
}

/**
 * A Needs-you row's line: what the agent needs, in its own words when it gave some. `needs_decision`
 * is a question the web app answers (Keep it, Skip); `needs_human` is an agent stopped mid-apply,
 * waiting for you in its own chat (a login, an upload), which this app cannot do for it.
 */
export function needsYouLine(status: string, reason: string | null | undefined): string | null {
  const said = reason?.trim();
  if (status === "needs_decision") {
    return said ? `Your agent asks: ${said}` : "Your agent has a question about this job.";
  }
  if (status === "needs_human") {
    return said ? `Your agent stopped: ${said}` : "Your agent stopped and needs you to finish a step.";
  }
  return null;
}

/** The Needs-you lane's help: how each kind present is answered, once each. */
export function needsYouHelp(statuses: readonly string[]): string[] {
  const help: string[] = [];
  if (statuses.includes("needs_decision")) {
    help.push("Keep it answers yes: the job goes back to To review. Skip answers no.");
  }
  if (statuses.includes("needs_human")) {
    help.push("Where your agent stopped, finish that step in your agent's own chat. It carries on from there.");
  }
  return help;
}
