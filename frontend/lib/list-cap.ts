/**
 * A list fetched with `?limit=`: how many rows came back, the limit asked
 * for, what they are, and the server's count of all of them when the
 * endpoint reports one (`/api/proposals` does; `/api/applications` and
 * `/api/jobs` return a bare array).
 */
export type ListCap = {
  loaded: number;
  limit: number;
  /** Plural, lower case: "applications", "saved jobs", "proposals". */
  noun: string;
  total?: number | null;
  /**
   * Which end the endpoint returns first, and so which rows a full page left
   * out. Most lists come newest first (the older ones are missing); the
   * Career history draft inbox comes oldest first (the newer ones are).
   */
  order?: "newest" | "oldest";
};

/**
 * Whether rows may be missing. With a total, the answer is exact. Without
 * one, a full page counts as capped: a list of exactly `limit` rows reads as
 * capped too, and the sentence below stays true for it.
 */
export function isListCapped({ loaded, limit, total }: ListCap): boolean {
  return total != null ? total > loaded : loaded >= limit;
}

/**
 * The notice, or null when nothing was left out. It speaks of what is
 * LOADED, not what is shown, so it stays true under any filter or search,
 * and when a filter shows nothing.
 */
export function listCapSentence(cap: ListCap): string | null {
  if (!isListCapped(cap)) return null;
  const loaded = cap.loaded.toLocaleString("en-US");
  const [end, missing] =
    cap.order === "oldest" ? ["oldest", "newer"] : ["most recent", "older"];
  const tail = `so ${missing} ones don't appear in this list.`;
  return cap.total != null
    ? `Only the ${loaded} ${end} of your ${cap.total.toLocaleString("en-US")} ${cap.noun} are loaded, ${tail}`
    : `Only your ${loaded} ${end} ${cap.noun} are loaded, ${tail}`;
}
