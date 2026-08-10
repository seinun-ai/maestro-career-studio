import type { ResumeData } from "@/lib/types";

function enabledIndices(
  entries: { enabled?: boolean }[] | undefined | null,
): number[] {
  return (entries ?? [])
    .map((e, i) => (e.enabled !== false ? i : -1))
    .filter((i) => i >= 0);
}

/**
 * Mirror of `backend/app/services/health_zones.hot_locations`. Keep the two in
 * step — this one exists so the editor can explain the health report's ordering
 * without a round trip, not as a second opinion.
 *
 * Summary, plus whichever section carries this candidate's evidence: the most
 * recent ROLE for an experienced candidate, PROJECTS for an early-career one,
 * because with no employment history the projects are the experience. One
 * choice, not both — the previous rule gave early-career resumes their first
 * role AND every project, which made most of a junior document hot and left
 * `cost()` with nothing cold to rank against.
 *
 * Returns location keys: "summary", or "<section>:<index>:<bullet_index>".
 */
export function hotZoneKeys(
  data: ResumeData,
  tier: string | null | undefined,
): Set<string> {
  const hot = new Set<string>(["summary"]);
  const section = tier === "early" ? "projects" : "experience";
  const entries = section === "projects" ? data.projects : data.experience;
  const indices = enabledIndices(entries);
  if (indices.length > 0) {
    const first = indices[0];
    const count = entries?.[first]?.bullets?.length ?? 0;
    for (let bi = 0; bi < count; bi++) hot.add(`${section}:${first}:${bi}`);
  }
  return hot;
}

export function isBulletHot(
  hot: Set<string>,
  section: string,
  index: number,
  bulletIndex: number,
): boolean {
  return hot.has(`${section}:${index}:${bulletIndex}`);
}
