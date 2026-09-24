import type { Proposal } from "./types";

/**
 * The Agent inbox's filters, pure so `node --test` runs them
 * (lib/inbox-filter.test.ts); pinned by test_frontend_agent_inbox.py.
 */

/** Score floors the toolbar offers ("Score 70+"): a preset Select keeps the
 *  toolbar one row of the same control, as on Jobs. */
export const SCORE_FLOORS = [50, 60, 70, 80] as const;
export type ScoreFloor = (typeof SCORE_FLOORS)[number];

/** The chosen base's score from the proposal's fit, or null when the agent
 *  recorded none. */
export function chosenScore(p: Pick<Proposal, "fit_json">): number | null {
  const fit = (p.fit_json ?? {}) as Record<string, unknown>;
  const chosen = fit.chosen_base;
  const scores = fit.scores;
  if (typeof chosen !== "string" || !scores || typeof scores !== "object") {
    return null;
  }
  const value = (scores as Record<string, unknown>)[chosen];
  return typeof value === "number" ? value : null;
}

export function boardHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

export type InboxFilter = {
  q: string;
  role: string;
  board: string;
  minScore: number | null;
};

type FilterableJob = Pick<Proposal["job"], "company" | "title" | "role_category" | "source_url">;

export function filterProposals<T extends Pick<Proposal, "fit_json"> & { job: FilterableJob }>(
  items: T[],
  { q, role, board, minScore }: InboxFilter,
): T[] {
  const needle = q.trim().toLowerCase();
  return items.filter((p) => {
    if (role !== "all" && p.job.role_category !== role) return false;
    if (board !== "all" && boardHost(p.job.source_url) !== board) return false;
    if (minScore != null) {
      const score = chosenScore(p);
      if (score == null || score < minScore) return false;
    }
    if (needle && !`${p.job.company ?? ""} ${p.job.title ?? ""}`.toLowerCase().includes(needle)) {
      return false;
    }
    return true;
  });
}
