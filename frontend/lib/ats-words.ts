/**
 * The ATS engine's keys in words (docs/frontend-conventions.md, Microcopy
 * rules: raw keys never reach the screen). The keys are the engine's
 * (`backend/app/services/ats/layers.py`, `SkillEvidence.placement` and
 * `.fix_hint`, and the subscore keys); the Score and tailor tab, the Resume
 * tab's before-and-after card and the gap page's evidence line all read these,
 * so one thing says one word on each.
 */

/**
 * "ATS score" spelled out once per surface, where it first shows (conventions: Canonical terms). It is
 * the app's own estimate, not a reading from an employer's system: `services/ats` scores the resume.
 */
export const ATS_SCORE_LEAD =
  "An ATS score (0 to 100) is our estimate of how an applicant tracking system would rate each resume for this job.";

/** The same, where a surface shows scores across many jobs (Analytics › Resume fit). */
export const ATS_SCORE_LEAD_ALL_JOBS =
  "An ATS score (0 to 100) is our estimate of how an applicant tracking system would rate a resume for a job.";

/** The ATS score's parts, in the order both score cards draw them. */
export const SUBSCORE_LABELS: {
  key: "keyword" | "placement_recency" | "semantic_fit" | "title" | "format";
  label: string;
}[] = [
  { key: "keyword", label: "Keywords" },
  { key: "placement_recency", label: "Recent experience" },
  { key: "semantic_fit", label: "Job duties covered" },
  { key: "title", label: "Job title" },
  { key: "format", label: "Format" },
];

const PLACEMENT_LABELS: Record<string, string> = {
  dual: "Skills and experience",
  experience_only: "Experience",
  skills_list_only: "Skills list only",
  undated_only: "Undated item",
  extra_only: "Other section",
  credential_only: "Certification",
};

const FIX_HINT_LABELS: Record<string, string> = {
  absent: "Not on your resume",
  mirror_wording: "Use the job's words",
  dual_place: "Show it in your experience too",
  resurface_recent: "Show a recent use",
  // Routed to the same intervention as resurface_recent (gap_analysis._HINT_TO_CATEGORY).
  credential_only: "Show a recent use",
  // Evidence only in an Other section: the fix is the same move into a dated entry.
  extra_only: "Show it in your experience",
  adjacent_available: "Name the related skill",
};

/** Where a matched skill was found, or null for a key this map lacks. */
export function placementLabel(key: string | null | undefined): string | null {
  return (key && PLACEMENT_LABELS[key]) || null;
}

/** What would fix a skill the resume misses, or null for a key this map lacks. */
export function fixHintLabel(key: string | null | undefined): string | null {
  return (key && FIX_HINT_LABELS[key]) || null;
}

const REQUIREMENT_LABELS: Record<string, string> = {
  required: "Required",
  preferred: "Preferred",
  mentioned: "Mentioned",
};

/** How strongly the job asks for a skill (`schemas/job_extraction.RequirementLevel`). */
export function requirementLabel(key: string | null | undefined): string | null {
  return (key && REQUIREMENT_LABELS[key]) || null;
}
