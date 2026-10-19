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

/** How much of the keeper the toast quotes before it trails off. */
const TOAST_QUOTE_MAX = 80;

/**
 * `folded` is how many were combined INTO the keeper; the sentence counts the keeper too. The
 * keeper is quoted without its own full stop, and a long one is cut at a word with an ellipsis.
 */
export function combinedToast(folded: number, keeperText: string): string {
  let quote = keeperText.trim().replace(/\.+$/, "");
  if (quote.length > TOAST_QUOTE_MAX) {
    const cut = quote.slice(0, TOAST_QUOTE_MAX);
    const space = cut.lastIndexOf(" ");
    quote = `${(space > TOAST_QUOTE_MAX / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, "")}…`;
  }
  return `Combined ${folded + 1} bullets into one. \u201c${quote}\u201d stays.`;
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
