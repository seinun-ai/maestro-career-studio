"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { NEEDS_YOU_STATUSES } from "@/lib/needs-you";
import type { ProposalListResponse } from "@/lib/types";

/**
 * How many proposals wait on the user, for the sidebar's Agent inbox badge.
 *
 * `limit=1`: the list endpoint counts the whole filtered set in `total` before
 * paging, after the same lazy expiry as the inbox. The key sits under
 * ["proposals"], so every triage invalidation refreshes it. A connected agent
 * changes proposals from outside this tab, hence the minute poll, which
 * react-query pauses while the tab is hidden.
 */
export function useNeedsYouCount(): number | null {
  const { data } = useQuery({
    queryKey: ["proposals", "needs-you-count"],
    queryFn: () =>
      apiFetch<ProposalListResponse>(
        `/api/proposals?status=${NEEDS_YOU_STATUSES.join(",")}&limit=1`,
      ),
    select: (page) => page.total,
    refetchInterval: 60_000,
  });
  return data ?? null;
}
