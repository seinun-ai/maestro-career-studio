/**
 * The base-to-tailored resume diff's words and identities, shared by the studio's review mode and the job page's
 * step 3. Pure, so `node --test` loads it; it imports only types, which the loader erases.
 */
import type { ResumeDiffHunk } from "./types";

export const SECTION_LABELS: Record<string, string> = {
  summary: "Summary",
  contact: "Contact",
  skills: "Skills",
  experience: "Experience",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
  extra_sections: "Other sections",
};

export const KIND_LABELS: Record<ResumeDiffHunk["kind"], string> = {
  summary_changed: "Summary rewritten",
  contact_changed: "Contact details changed",
  bullet_added: "Bullet added",
  bullet_removed: "Bullet removed",
  bullet_edited: "Bullet reworded",
  entry_added: "Item added",
  entry_removed: "Item removed",
  entry_enabled: "Item shown",
  entry_disabled: "Item hidden",
  skills_group_changed: "Skill group changed",
  extra_section_added: "Section added",
  extra_section_removed: "Section removed",
  extra_section_changed: "Section changed",
  extra_section_enabled: "Section shown",
  extra_section_disabled: "Section hidden",
};

/** Where a change sits: its section, the item a bullet belongs to (its company, name, institution or title, read
 *  from the draft at the hunk's entry index) and what happened. "Experience · Seinun LLC · Bullet added". */
export function hunkPlace(hunk: ResumeDiffHunk, draft: Record<string, unknown> | null): string {
  const list = draft?.[hunk.section];
  const owner =
    hunk.kind.startsWith("bullet_") && hunk.section !== "certifications" && hunk.index != null && Array.isArray(list)
      ? (list[hunk.index] as Record<string, unknown> | undefined)
      : undefined;
  const ownerName = owner
    ? [owner.company, owner.name, owner.institution, owner.title].find((v): v is string => typeof v === "string" && !!v)
    : undefined;
  return [SECTION_LABELS[hunk.section] ?? hunk.section, ownerName, KIND_LABELS[hunk.kind]].filter(Boolean).join(" · ");
}

/** A short, stable hash of a string (djb2, base 36): enough to tell two hunks' texts apart in a key. */
function textHash(text: string): string {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

/**
 * One id per hunk that ignores its position in the list: kind, section, entry index and a hash of its two sides.
 * A revert removes one row and the rows after it keep their ids, so React keeps their nodes and focus can move to
 * a neighbour. Two identical hunks (the same bullet added twice) are told apart by their order among themselves.
 */
export function hunkIds(hunks: readonly ResumeDiffHunk[]): string[] {
  const seen = new Map<string, number>();
  return hunks.map((hunk) => {
    const base = `${hunk.kind}:${hunk.section}:${hunk.index ?? ""}:${textHash(JSON.stringify([hunk.before, hunk.after]))}`;
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return n === 0 ? base : `${base}#${n}`;
  });
}

/**
 * Whether the diff on screen describes the draft a revert would edit: it was fetched no earlier than the job
 * detail that brought this draft (`draftLoadedAt`, the detail's `dataUpdatedAt` when the application's
 * `updated_at` last changed). A revert matches by position and text, so one against an older diff could undo the
 * wrong thing. Zero means "not loaded": never current.
 */
export function diffIsCurrent(diffUpdatedAt: number, draftLoadedAt: number): boolean {
  return diffUpdatedAt > 0 && diffUpdatedAt >= draftLoadedAt;
}
