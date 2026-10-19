/**
 * A bullet's wordings on the entity page: the chip, what each wording offers, the split request
 * and which bullets the list shows at all. Pure (`kb-wordings.test.ts`).
 */
import type { KBPointOut, KBWordingOut, UUID } from "./types";

export function wordingsChip(wordings: readonly KBWordingOut[]): string | null {
  const n = wordings.length;
  return n === 0 ? null : `${n} ${n === 1 ? "wording" : "wordings"}`;
}

/** An older copy a resume still carries cannot be adopted: it would revert a KB edit. */
export const PLACED_HINT = "Add to a resume to update it";

export function wordingActions(w: KBWordingOut): { adopt: boolean; split: boolean; hint: string | null } {
  return { adopt: w.adoptable, split: w.splittable, hint: w.kind === "placed" ? PLACED_HINT : null };
}

export type SplitRequest =
  | { kind: "split-wording"; pointId: UUID; text: string; resumeKey: string | null }
  | { kind: "unmerge"; pointId: UUID };

/** Make its own bullet: a resume wording splits off the claim; a combined claim comes back. */
export function splitRequest(claimId: UUID, w: KBWordingOut): SplitRequest | null {
  if (!w.splittable) return null;
  if (w.kind === "merged" && w.point_id) return { kind: "unmerge", pointId: w.point_id };
  // Every row with this text follows the words, whichever resume carried it: one row per text
  // is what the popover shows, so one click moves the whole row.
  return { kind: "split-wording", pointId: claimId, text: w.text, resumeKey: null };
}

/** The list hides a retired bullet that was combined into another: it is that bullet's wording. */
export function visibleClaims<T extends Pick<KBPointOut, "merged_into_point_id">>(points: readonly T[]): T[] {
  return points.filter((p) => p.merged_into_point_id === null);
}
