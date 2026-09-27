import {
  emptyMetricAsk,
  metricContextFromValue,
  type MetricAskValue,
} from "@/components/resume-health/metric-ask-input";
import { apiFetch } from "@/lib/api";
import {
  answerMatchesFinding,
  changesText,
  isMetricAsk,
  textAtLocation,
  type PassStatus,
  type StoredAskAnswer,
} from "@/lib/health-report";
import type { BaseResumeDetail, DisputeResult, LintFinding, ResumeData } from "@/lib/types";

/** One row of the question pass: an ask, what the user typed, and where its new wording stands. */
export type PassRow = {
  /** The row's identity for this visit: the finding id it opened with (Write it again can swap the finding). */
  key: string;
  finding: LintFinding;
  /** The bullet as the check read it: the diff's left side and the text the op replaces. */
  original: string | null;
  metric: MetricAskValue;
  answer: string;
  useAlternative: boolean;
  /** Skip for now: this visit only. The row still counts, is never drafted, and comes back next time. */
  skipped: boolean;
  status: PassStatus;
  suggestion: string | null;
  /** Edit's text, once the user opened Edit. */
  edited: string | null;
};

export const rowContext = (row: PassRow) =>
  isMetricAsk(row.finding) && !row.useAlternative ? metricContextFromValue(row.metric) : row.answer.trim();
export const rowText = (row: PassRow) => row.edited ?? row.suggestion ?? "";
/** Other sections have no bullet edit op: their new wording is copied by hand. */
export const copyOnly = (row: PassRow) => row.finding.location.section.startsWith("extra:");
/** The wording can be saved from this row: drafted, appliable, and it changes the bullet. */
export const canSave = (row: PassRow) =>
  row.status === "drafted" && !copyOnly(row) && changesText(row.original, rowText(row));
export const sameWhere = (a: LintFinding["location"], b: LintFinding["location"]) =>
  a.section === b.section &&
  (a.index ?? null) === (b.index ?? null) &&
  (a.bullet_index ?? null) === (b.bullet_index ?? null);

export function isAnswered(row: PassRow, disputes: Record<string, DisputeResult>): boolean {
  if (row.status === "drafted" || row.status === "saving" || row.status === "saved") return true;
  if (row.finding.content_hash && disputes[row.finding.content_hash]) return true;
  return rowContext(row).length > 0;
}

export function initialRow(finding: LintFinding, data: ResumeData, stored: StoredAskAnswer | undefined): PassRow {
  // An answer drafted on an earlier visit (or on the report's card) comes back with its new wording.
  const fresh = answerMatchesFinding(stored, finding.content_hash);
  const metricAsk = isMetricAsk(finding);
  return {
    key: finding.id,
    finding,
    original: textAtLocation(data, finding),
    metric:
      fresh && metricAsk ? { ...emptyMetricAsk(), somethingElse: true, freeText: stored.answer } : emptyMetricAsk(),
    answer: fresh && !metricAsk ? stored.answer : "",
    useAlternative: false,
    skipped: false,
    status: fresh && stored.suggestion ? "drafted" : "answering",
    suggestion: fresh ? (stored.suggestion ?? null) : null,
    edited: null,
  };
}

export const fetchBase = (resumeKey: string) => apiFetch<BaseResumeDetail>(`/api/base-resumes/${resumeKey}`);
