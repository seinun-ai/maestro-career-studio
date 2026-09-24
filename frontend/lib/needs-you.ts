import type { ProposalStatus } from "./types";

/**
 * What waits on the user. One list for the Agent inbox's Needs you lane and
 * the sidebar's count, so the two can never disagree about which statuses
 * count. Pure (lib/needs-you.test.ts); pinned by test_frontend_agent_inbox.py.
 */
export const NEEDS_YOU_STATUSES: readonly ProposalStatus[] = ["needs_decision", "needs_human"];
