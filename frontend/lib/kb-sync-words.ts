/**
 * The studio's Add to career history pill in words: what is ready to add, and what an add did. Pure, so
 * `node --test` runs it (`kb-sync-words.test.ts`).
 */
import type { SyncResult, SyncStatus } from "./types";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "9 bullets, 5 skills": the number on the pill, spelled out. New items, new skills and unnoted
 *  rewordings: never `recorded_drift`, which the career history already notes. */
export function syncActionableCount(status: SyncStatus): number {
  return status.counts.new + status.counts.drift + status.counts.skills_new;
}

/** The pill: "Add 14 things to career history" ("Add to career history (14)" read as a count of
 *  nothing in particular). "Things", not "items": an item is one career history record, and these
 *  are bullets, skills and records together; the popover splits them. */
export function syncPillLabel(count: number): string {
  return `Add ${plural(count, "thing", "things")} to career history`;
}

/** Section → its noun, one and many. The lines add up to the pill's number. */
const SECTION_NOUNS: [section: string, one: string, many: string][] = [
  ["experience", "experience bullet", "experience bullets"],
  ["projects", "project bullet", "project bullets"],
  ["education", "education item", "education items"],
  ["certifications", "certification", "certifications"],
  ["extra", "item in other sections", "items in other sections"],
];

/** The popover's lines under "Ready to add to your career history". */
export function syncBreakdownLines(status: SyncStatus): string[] {
  const counted = new Map<string, number>();
  for (const item of status.items) {
    if (item.tier !== "new") continue;
    counted.set(item.section, (counted.get(item.section) ?? 0) + 1);
  }
  const lines: string[] = [];
  for (const [section, one, many] of SECTION_NOUNS) {
    const n = counted.get(section) ?? 0;
    if (n > 0) lines.push(plural(n, one, many));
  }
  const skills = status.counts.skills_new;
  if (skills > 0) lines.push(plural(skills, "skill", "skills"));
  // Says what adding will DO, because "drifted" alone reads like a problem.
  const drift = status.counts.drift;
  if (drift > 0) lines.push(`${plural(drift, "reworded bullet", "reworded bullets")} (we'll note the change)`);
  // The tier vocabulary is the server's; a shape this list does not name still says how much there is.
  if (lines.length === 0) lines.push(`${syncActionableCount(status)} to add`);
  return lines;
}

function joinWords(parts: string[]): string {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * What an add did, from every count the server returns: draft bullets (`created`), new items
 * (`items_added`: an education or certification add writes an item and no bullet), skills
 * (`skills_added`, never the category list) and noted rewordings. Never "Added 0 new bullets".
 */
export function syncResultSentence(result: SyncResult): string {
  const added = [
    result.created > 0 ? plural(result.created, "draft bullet", "draft bullets") : null,
    result.items_added > 0 ? plural(result.items_added, "item", "items") : null,
    result.skills_added.length > 0 ? plural(result.skills_added.length, "skill", "skills") : null,
  ].filter((part): part is string => part !== null);
  const sentences = [
    added.length > 0 ? `Added ${joinWords(added)} to your career history.` : null,
    result.drifted > 0 ? `Noted ${plural(result.drifted, "wording change", "wording changes")}.` : null,
  ].filter((part): part is string => part !== null);
  return sentences.length > 0 ? sentences.join(" ") : "Nothing new to add. Your career history already has all of this.";
}
