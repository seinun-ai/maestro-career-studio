/**
 * Profile's tiles and folds (board "Profile, facts about you"), and which one holds each deep-link anchor.
 * No imports: `node --test` loads it as it is (profile-tiles.test.ts).
 *
 * A tile opens its editor under the grid, one at a time; a fold opens in place. The first anchor of each is
 * its card's id (`anchorHref("/profile", "autofill-work_auth")`, the ids setup-steps.ts and the job knock-out
 * card aim at, kept from the Autofill tab); ids INSIDE a card resolve by prefix (`job-preferences-years`).
 * `autofill` is the tiles themselves (the old Autofill card), so it opens nothing.
 */
export type ProfileSection = {
  id: string;
  title: string;
  anchors: readonly string[];
  prefixes: readonly string[];
};

export const PROFILE_TILES = [
  { id: "contact", title: "Contact", anchors: ["autofill-personal"], prefixes: ["af-personal-"] },
  { id: "where", title: "Where you apply", anchors: ["market"], prefixes: ["market-"] },
  { id: "permits", title: "Work permits", anchors: ["autofill-work_auth"], prefixes: ["af-permit-"] },
  { id: "jobs", title: "Jobs you want", anchors: ["job-preferences"], prefixes: ["job-preferences-"] },
  { id: "persona", title: "How you come across", anchors: ["persona"], prefixes: ["persona-"] },
  { id: "start", title: "Start and pay", anchors: ["autofill-preferences"], prefixes: ["af-preferences-"] },
  { id: "education", title: "Education", anchors: ["autofill-education"], prefixes: ["af-education-"] },
  { id: "languages", title: "Languages", anchors: ["autofill-languages"], prefixes: ["af-languages-"] },
  { id: "questions", title: "Your own questions", anchors: ["autofill-custom"], prefixes: ["af-custom-"] },
] as const satisfies readonly ProfileSection[];

export const PROFILE_FOLDS = [
  { id: "diversity", title: "Diversity questions", anchors: ["autofill-eeo"], prefixes: ["af-eeo-"] },
  { id: "eligibility", title: "Eligibility", anchors: ["autofill-eligibility"], prefixes: ["af-eligibility-"] },
] as const satisfies readonly ProfileSection[];

export type TileId = (typeof PROFILE_TILES)[number]["id"];
export type FoldId = (typeof PROFILE_FOLDS)[number]["id"];

/** A tile's or fold's card id: the anchor its deep links name. */
export function cardId(section: ProfileSection): string {
  return section.anchors[0];
}

function holds(section: ProfileSection, anchor: string): boolean {
  return section.anchors.includes(anchor) || section.prefixes.some((prefix) => anchor.startsWith(prefix));
}

/** The tile or fold that renders `anchor`, or null (`autofill`, `#main-content`, an unknown id). */
export function sectionForAnchor(
  anchor: string,
): { kind: "tile"; id: TileId } | { kind: "fold"; id: FoldId } | null {
  if (!anchor) return null;
  const tile = PROFILE_TILES.find((section) => holds(section, anchor));
  if (tile) return { kind: "tile", id: tile.id };
  const fold = PROFILE_FOLDS.find((section) => holds(section, anchor));
  return fold ? { kind: "fold", id: fold.id } : null;
}
