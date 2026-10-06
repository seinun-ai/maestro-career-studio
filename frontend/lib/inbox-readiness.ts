// Readiness on the Agent inbox's rows (backend services/inbox_readiness.py owns the rule; this is
// its twin for sorting and words). `node --test` loads it directly; imports are types only.
import type { ProposalStatus } from "./types";

export type Readiness = {
  tailored: boolean | null;
  knockout: string | null;
  to_check: number;
  /** The job's country when the application's resume is set for another one. Optional: an older backend omits it. */
  base_country?: string | null;
};
export type ReadinessMark = { text: string; tone: "warning" | "error" };

const KNOCKOUT_WORDS: Record<string, string> = {
  work_authorization: "work authorization",
  opt: "OPT",
  salary: "salary",
  experience: "experience",
  on_site: "on-site",
};

/** The reason the backend closes a proposal with when you applied yourself (services/proposals.py). */
export const APPLIED_MANUALLY = "applied manually";

export function isReady(r: Readiness | null | undefined): boolean {
  return !!r && r.tailored === true && r.knockout == null && r.to_check === 0 && r.base_country == null;
}

export function readinessMarks(r: Readiness | null | undefined): ReadinessMark[] {
  if (!r) return [];
  const marks: ReadinessMark[] = [];
  if (r.knockout) {
    const word = KNOCKOUT_WORDS[r.knockout];
    marks.push({ text: word ? `Knock-out: ${word}` : "Knock-out", tone: "error" });
  }
  if (r.base_country) marks.push({ text: "Resume for another country", tone: "warning" });
  if (r.to_check > 0) marks.push({ text: `${r.to_check} to check`, tone: "warning" });
  return marks;
}

/** The three readiness steps as a meter: tailored, nothing blocks it (no knock-out, and the resume is set for the
 *  job's country), answers checked. So the meter is full only when the row `isReady`. Null without readiness. */
export function readinessSteps(r: Readiness | null | undefined): { done: number; total: 3 } | null {
  if (!r) return null;
  const unblocked = r.knockout == null && r.base_country == null;
  const done = [r.tailored === true, unblocked, r.to_check === 0].filter(Boolean).length;
  return { done, total: 3 };
}

/** Ready rows first; each group keeps the order it came in (the user's chosen sort). */
export function readyFirst<T extends { readiness?: Readiness | null }>(items: readonly T[]): T[] {
  return [...items.filter((i) => isReady(i.readiness)), ...items.filter((i) => !isReady(i.readiness))];
}

/** History's chip: Applied yourself for a job you applied to outside the agent. */
export function historyLabel(status: string, reason: string | null | undefined, fallback: string): string {
  return status === "rejected" && reason === APPLIED_MANUALLY ? "Applied yourself" : fallback;
}

/** History groups manual applies with Applied while keeping the stored status unchanged. */
export function historyStatusOf(
  status: ProposalStatus,
  reason: string | null | undefined,
): ProposalStatus {
  return status === "rejected" && reason === APPLIED_MANUALLY ? "submitted" : status;
}

/** Created after the last visit. No visit time known yet: nothing is marked new. */
export function isNew(createdAt: string, since: string | null): boolean {
  return since != null && Date.parse(createdAt) > Date.parse(since);
}
