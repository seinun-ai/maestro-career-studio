"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { ProposalFunnel } from "@/lib/types";

/** The proposal funnel. Two readers share this one cache entry: the Agent
 *  inbox's "Cap today" line and Analytics › Overview's Agent pipeline card.
 *  Under ["proposals"], so every triage invalidation refreshes both. */
export function useProposalFunnel() {
  return useQuery({
    queryKey: ["proposals", "funnel"],
    queryFn: () => apiFetch<ProposalFunnel>("/api/proposals/funnel"),
  });
}
