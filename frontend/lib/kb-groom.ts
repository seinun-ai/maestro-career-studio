/**
 * The Tidy bullets dialog's decisions (`kb-groom.test.ts`): which ids Combine sends, which Not the
 * same sends, which state the dialog is in, and the toast.
 */
import type { GroomCluster, GroomMember, GroomReport, KBCombineResponse, KBPointState, UUID } from "./types";

/** Every member except the one the user keeps. */
export function otherIds(cluster: GroomCluster, keeperId: UUID): UUID[] {
  return cluster.members.filter((m) => m.id !== keeperId).map((m) => m.id);
}

/** The ids the keep-apart endpoint pairs among itself (a cluster of three records three pairs). */
export function pairsOf(cluster: GroomCluster): UUID[] {
  return cluster.members.map((m) => m.id);
}

export type GroomState = "clusters" | "empty" | "failed";

export function groomState(report: GroomReport): GroomState {
  if (!report.compared_wording) return "failed";
  return report.clusters.length === 0 ? "empty" : "clusters";
}

/** `folded` is how many were combined INTO the keeper; the sentence counts the keeper too. */
export function combinedToast(folded: number, keeperText: string): string {
  return `Combined ${folded + 1} bullets into one. ${keeperText} stays.`;
}

/** The keeper rule, stated so the proposal is explainable. */
export const KEEPER_RULE =
  "We suggest keeping the approved one, then the most recently edited, then the longest.";

/**
 * Undo of a Combine: every loser goes back to its prior state (leaving `retired` clears its
 * pointer server-side), then the combined claims the flatten moved off a loser are combined
 * back onto it. `repointed` is the combine response's list.
 */
export function undoCombinePlan(
  losers: readonly Pick<GroomMember, "id" | "state">[],
  repointed: readonly KBCombineResponse["repointed"][number][],
): { restore: { id: UUID; state: KBPointState }[]; recombine: { keeperId: UUID; pointIds: UUID[] }[] } {
  const byLoser = new Map<UUID, UUID[]>();
  for (const r of repointed) byLoser.set(r.from_id, [...(byLoser.get(r.from_id) ?? []), r.point_id]);
  return {
    restore: losers.map((m) => ({ id: m.id, state: m.state })),
    recombine: [...byLoser.entries()].map(([keeperId, pointIds]) => ({ keeperId, pointIds })),
  };
}
