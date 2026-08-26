/**
 * Pure helpers for the health report page. Keep this file free of React so
 * Node's type-stripped test runner can import it.
 *
 * LEVEL_VALUES is duplicated in health-zones.ts (the designated Python
 * mirror) — both must stay in lockstep with health_score.LEVEL_VALUES.
 */

import type { ResumeData } from "./types";

export const LEVEL_VALUES: Record<string, number> = {
  direct: 1.0,
  analogue: 0.8,
  adjacent: 0.5,
  implied: 0.3,
  unaddressed: 0.0,
};

export type ScoreBreakdown = {
  raw_score: number;
  e_hot: number | null;
  n_scoreable: number;
  capped_by: "fatal" | "serious" | null;
};

export type StreamFilter = "all" | "fix" | "ask" | "note";

export const CONTENT_CHANGED_PREFIX = "content changed since analysis";

export const STALE_APPLY_HINT =
  "This text changed since the analysis — re-analyze before applying.";

export const CONTENT_CHANGED_HINT =
  "This text changed since the analysis — re-analyze to get fresh suggestions";

/** Backend may land after this branch: missing `stale` is current, not stale. */
export function reportIsStale(report: { stale?: boolean } | null | undefined): boolean {
  return report?.stale === true;
}

export function reportInsufficientEvidence(
  report: { insufficient_evidence?: boolean } | null | undefined,
): boolean {
  return report?.insufficient_evidence === true;
}

export function isContentChangedError(err: {
  status?: number;
  message?: string;
}): boolean {
  return (
    err.status === 409 &&
    (err.message ?? "").startsWith(CONTENT_CHANGED_PREFIX)
  );
}

/**
 * "mean evidence 88 · capped to 69 by one serious gate"
 * Returns null when the backend has not yet sent `score_breakdown`.
 */
export function scoreCompositionLine(
  score: number,
  breakdown: ScoreBreakdown | null | undefined,
): string | null {
  if (!breakdown) return null;
  if (breakdown.capped_by) {
    return `mean evidence ${breakdown.raw_score} · capped to ${score} by one ${breakdown.capped_by} gate`;
  }
  return `mean evidence ${breakdown.raw_score}`;
}

export function potentialPoints(
  levelName: string | null | undefined,
  nScoreable: number | null | undefined,
): number | null {
  if (!levelName || nScoreable == null || nScoreable <= 0) return null;
  const value = LEVEL_VALUES[levelName];
  if (value == null) return null;
  return Math.round((100 * (1 - value)) / nScoreable);
}

export function levelNameOf(finding: {
  classification_level?: string | null;
  level?: number | null;
}): string | null {
  if (finding.classification_level) return finding.classification_level;
  if (finding.level == null) return null;
  for (const [name, value] of Object.entries(LEVEL_VALUES)) {
    if (value === finding.level) return name;
  }
  return null;
}

/** Location group key. Order of groups is first appearance in the input list. */
export function groupKey(finding: {
  location: { section: string; index?: number | null };
}): string {
  const { section, index } = finding.location;
  if (section === "summary") return "summary";
  if (section === "skills") return "skills";
  if (section === "certifications") return "certifications";
  if (section.startsWith("extra:")) return section;
  if (index != null) return `${section}:${index}`;
  return section;
}

export type FindingGroup<T> = { key: string; findings: T[] };

export function groupFindings<
  T extends { location: { section: string; index?: number | null } },
>(findings: T[]): FindingGroup<T>[] {
  const order: string[] = [];
  const buckets = new Map<string, T[]>();
  for (const finding of findings) {
    const key = groupKey(finding);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = [];
      buckets.set(key, bucket);
      order.push(key);
    }
    bucket.push(finding);
  }
  return order.map((key) => ({ key, findings: buckets.get(key)! }));
}

export function sharedCoaching(
  findings: { why: string; how: string }[],
): { why: string; how: string } | null {
  if (findings.length === 0) return null;
  const why = findings[0].why;
  const how = findings[0].how;
  if (!why && !how) return null;
  if (findings.every((f) => f.why === why && f.how === how)) {
    return { why, how };
  }
  return null;
}

/**
 * Group-header blurb when every finding shares issue + how.
 *
 * The backend's `issue` strings are complete sentences with varying subjects
 * ("Has a scale metric…", "A reader can't tell what you did here.") — they
 * CANNOT be conjugated into a count-led sentence, which is how this shipped
 * "2 items here are a reader can't tell what you did here". Both copy strings
 * are therefore reproduced verbatim; the count is introduced with a colon,
 * which is agreement-free. The rail's jump list already carries counts, so a
 * plural-shaped sentence buys nothing.
 */
export function hoistBlurb(
  findings: { issue: string; how: string }[],
): string | null {
  if (findings.length === 0) return null;
  const issue = findings[0].issue;
  const how = findings[0].how;
  if (!issue && !how) return null;
  if (!findings.every((f) => f.issue === issue && f.how === how)) return null;
  const count = findings.length;
  const how1 =
    count > 1 ? how.replace(/\bthis bullet\b/gi, "each bullet") : how;
  const body = [issue, how1].filter(Boolean).join(" ");
  if (count === 1) return body;
  const lowered = issue ? issue.charAt(0).toLowerCase() + issue.slice(1) : "";
  return `${count} bullets here: ${[lowered, how1].filter(Boolean).join(" ")}`;
}

/**
 * The part of a finding label that the group header does NOT already say.
 * Labels arrive as "<entry> · bullet N"; the header names the entry, so the
 * collapsed row shows only the tail. Without this a long entry name ("Bone
 * Muscle Research Center — Research Assistant - Data Science & Bioinformatics")
 * eats the whole row and pushes the chips and action past the card edge.
 */
export function shortFindingLabel(label: string): string {
  const cut = label.lastIndexOf(" · ");
  if (cut < 0) return label;
  const tail = label.slice(cut + 3).trim();
  return tail || label;
}

export function groupTitle(key: string, data?: ResumeData | null): string {
  if (key === "summary") return "Summary";
  if (key === "skills") return "Skills";
  if (key === "certifications") return "Certifications";
  if (key.startsWith("extra:")) {
    const extraKey = key.slice("extra:".length);
    const section = data?.extra_sections?.find((s) => s.key === extraKey);
    return section?.title ?? extraKey;
  }
  const colon = key.indexOf(":");
  if (colon < 0) return key;
  const section = key.slice(0, colon);
  const index = Number(key.slice(colon + 1));
  if (Number.isNaN(index)) return key;
  if (section === "experience") {
    const entry = data?.experience?.[index];
    if (entry) {
      const label = [entry.role, entry.company].filter(Boolean).join(" · ");
      return label || `Experience ${index + 1}`;
    }
    return `Experience ${index + 1}`;
  }
  if (section === "projects") {
    return data?.projects?.[index]?.name ?? `Project ${index + 1}`;
  }
  if (section === "education") {
    return data?.education?.[index]?.institution ?? `Education ${index + 1}`;
  }
  return key;
}

export type NoteRuleGroup<T> = {
  rule: string;
  title: string;
  count: number;
  shapeNote: boolean;
  subjects: string[];
  notes: T[];
};

const RULE_TITLES: Record<string, string> = {
  "skills.undemonstrated": "Listed but never demonstrated",
  "skills.trailing_punct": "Trailing punctuation on a skill",
  "certifications.trailing_punct": "Trailing punctuation on a certification",
  "skills.duplicate_across_groups": "Skill listed in more than one group",
  "certifications.duplicate": "Duplicate certification",
  "skills.sentence_like": "Skill reads like a sentence",
  "bullet.too_long": "Bullet is too long",
  "bullet.too_short": "Bullet is too short",
  "entry.too_many_bullets": "Too many bullets",
  "summary.missing": "Summary is missing",
};

export function groupNotesByRule<
  T extends { rule?: string; subject?: string; label: string; issue: string },
>(notes: T[]): NoteRuleGroup<T>[] {
  const order: string[] = [];
  const buckets = new Map<string, T[]>();
  for (const note of notes) {
    const rule = note.rule ?? note.label;
    let bucket = buckets.get(rule);
    if (!bucket) {
      bucket = [];
      buckets.set(rule, bucket);
      order.push(rule);
    }
    bucket.push(note);
  }
  return order.map((rule) => {
    const list = buckets.get(rule)!;
    const subjects = list
      .map((n) => n.subject)
      .filter((s): s is string => Boolean(s));
    // A note with no `rule` is a shape note keyed by its label; the label IS
    // the human title ("Evidence concentrated in projects"), while its issue
    // is a bare statistic that reads as gibberish in a heading.
    const shapeNote = !list[0].rule;
    return {
      rule,
      title: shapeNote
        ? list[0].label
        : RULE_TITLES[rule] ?? list[0].issue.replace(/^"[^"]+"\s*/, "").replace(/\.$/, ""),
      count: list.length,
      shapeNote,
      subjects,
      notes: list,
    };
  });
}

const TRAILING_PUNCT_RUN = /[.,;…\s]+$/;

export function stripTrailingPunct(text: string): string {
  return text.replace(TRAILING_PUNCT_RUN, "").trimEnd();
}

export function isMechanicalPunctRule(rule: string): boolean {
  return (
    rule === "skills.trailing_punct" || rule === "certifications.trailing_punct"
  );
}

export type LintEditOp = Record<string, unknown>;

/** Ops that reuse existing /edits kinds to drop trailing punctuation. */
export function punctFixOps(
  rule: string,
  subjects: string[],
  data: ResumeData,
): LintEditOp[] | null {
  if (rule === "skills.trailing_punct") {
    const ops: LintEditOp[] = [];
    for (const group of data.skills ?? []) {
      const needles = new Set(
        subjects.filter((s) => group.items.includes(s)),
      );
      if (needles.size === 0) continue;
      ops.push({
        kind: "replace_skills_group",
        category: group.category,
        items: group.items.map((item) =>
          needles.has(item) ? stripTrailingPunct(item) : item,
        ),
      });
    }
    return ops.length > 0 ? ops : null;
  }
  if (rule === "certifications.trailing_punct") {
    const needles = new Set(subjects);
    const items = (data.certifications ?? []).map((item) =>
      needles.has(item) ? stripTrailingPunct(item) : item,
    );
    if (items.every((item, i) => item === (data.certifications ?? [])[i])) {
      return null;
    }
    return [{ kind: "replace_certifications", items }];
  }
  return null;
}

export function fatalGateFailed(gates: { tier: string; status: string }[] | undefined): boolean {
  return (gates ?? []).some((g) => g.tier === "fatal" && g.status === "fail");
}

export function filterFindings<T extends { type: string }>(
  findings: T[],
  filter: StreamFilter,
): T[] {
  if (filter === "all") return findings;
  return findings.filter((f) => f.type === filter);
}

export const METRIC_ASK_NEEDLE = "What number measures this";

export function isMetricAsk(question: string | null | undefined): boolean {
  return (question ?? "").includes(METRIC_ASK_NEEDLE);
}

export function isBulletSubjectRule(rule: string | undefined): boolean {
  return rule === "bullet.too_long" || rule === "bullet.too_short";
}

export type MetricUnit =
  | "users"
  | "rows"
  | "percent"
  | "hours"
  | "minutes"
  | "dollars"
  | "other";

export const METRIC_UNITS: { id: MetricUnit; label: string }[] = [
  { id: "users", label: "users" },
  { id: "rows", label: "rows" },
  { id: "percent", label: "%" },
  { id: "hours", label: "hours saved" },
  { id: "minutes", label: "minutes saved" },
  { id: "dollars", label: "$" },
  { id: "other", label: "other" },
];

export function composeMetricContext(parts: {
  amount: string;
  unit: MetricUnit;
  unitOther?: string;
  timeframe?: string;
}): string {
  const amount = parts.amount.trim();
  const other = (parts.unitOther ?? "").trim();
  let core = amount;
  switch (parts.unit) {
    case "users":
      core = `served ${amount} users`;
      break;
    case "rows":
      core = `processed ${amount} rows`;
      break;
    case "percent":
      core = `${amount}%`;
      break;
    case "hours":
      core = `saved ${amount} hours`;
      break;
    case "minutes":
      core = `saved ${amount} minutes`;
      break;
    case "dollars":
      core = `$${amount}`;
      break;
    case "other":
      core = other ? `${amount} ${other}` : amount;
      break;
  }
  const timeframe = (parts.timeframe ?? "").trim();
  return timeframe ? `${core} within ${timeframe}` : core;
}

export type StoredAskAnswer = {
  answer: string;
  suggestion: string | null;
  content_hash: string;
};

export function answerMatchesFinding(
  stored: StoredAskAnswer | undefined,
  contentHash: string | null | undefined,
): stored is StoredAskAnswer {
  return Boolean(stored && contentHash && stored.content_hash === contentHash);
}

type DeltaFinding = {
  type: string;
  location: { section: string; index?: number | null; bullet_index?: number | null };
  content_hash?: string | null;
  classification_level?: string | null;
  level?: number | null;
};

function findingIdentity(finding: DeltaFinding): string {
  const { section, index, bullet_index } = finding.location;
  return `${finding.content_hash ?? ""}|${section}|${index ?? ""}|${bullet_index ?? ""}`;
}

function isScoreableFinding(finding: DeltaFinding): boolean {
  if (finding.type === "note" || finding.type === "gate") return false;
  if (finding.location.section === "summary") return false;
  return (
    finding.level != null ||
    finding.classification_level != null ||
    Boolean(finding.content_hash)
  );
}

/** One sentence attributing a score change, or null when the diff is empty/ambiguous. */
export function explainScoreDelta(
  prior: DeltaFinding[],
  next: DeltaFinding[],
  titleFor: (groupKey: string) => string,
): string | null {
  const priorMap = new Map(
    prior.filter(isScoreableFinding).map((finding) => [findingIdentity(finding), finding]),
  );
  const nextMap = new Map(
    next.filter(isScoreableFinding).map((finding) => [findingIdentity(finding), finding]),
  );

  const entered: DeltaFinding[] = [];
  const resolved: DeltaFinding[] = [];
  let reclass = 0;

  for (const [key, finding] of nextMap) {
    const old = priorMap.get(key);
    if (!old) {
      entered.push(finding);
      continue;
    }
    const from = old.classification_level;
    const to = finding.classification_level;
    if (from && to && from !== to) reclass += 1;
  }
  for (const [key] of priorMap) {
    if (!nextMap.has(key)) {
      const old = priorMap.get(key);
      if (old) resolved.push(old);
    }
  }

  const clauses: string[] = [];
  if (entered.length > 0) {
    const byGroup = new Map<string, DeltaFinding[]>();
    for (const finding of entered) {
      const key = groupKey(finding);
      const list = byGroup.get(key) ?? [];
      list.push(finding);
      byGroup.set(key, list);
    }
    if (byGroup.size > 2) return null;
    for (const [key, list] of byGroup) {
      const levels = [
        ...new Set(
          list
            .map((finding) => finding.classification_level)
            .filter((level): level is string => Boolean(level)),
        ),
      ];
      const levelBit = levels.length === 1 ? ` at ${levels[0]}` : "";
      const n = list.length;
      clauses.push(
        `+${n} bullet${n === 1 ? "" : "s"} in ${titleFor(key)} entered${levelBit}`,
      );
    }
  }
  if (resolved.length > 0) {
    clauses.push(
      `${resolved.length} finding${resolved.length === 1 ? "" : "s"} resolved`,
    );
  }
  if (reclass > 0) {
    clauses.push(
      `${reclass} classification${reclass === 1 ? "" : "s"} changed`,
    );
  }
  if (clauses.length === 0 || clauses.length > 3) return null;
  const sentence = clauses.join("; ");
  return sentence.charAt(0).toUpperCase() + sentence.slice(1) + ".";
}


export function textAtLocation(
  data: ResumeData,
  finding: { location: { section: string; index?: number | null; bullet_index?: number | null } },
): string | null {
  const { section, index, bullet_index } = finding.location;
  if (section === "summary") return data.summary ?? "";
  if (section.startsWith("extra:")) {
    const key = section.slice("extra:".length);
    const sec = data.extra_sections?.find((s) => s.key === key);
    if (!sec) return null;
    if (sec.type === "bullets")
      return bullet_index != null ? (sec.bullets?.[bullet_index] ?? null) : null;
    if (index == null || bullet_index == null) return null;
    return sec.entries?.[index]?.bullets?.[bullet_index] ?? null;
  }
  if (index == null || bullet_index == null) return null;
  const entries =
    section === "experience"
      ? data.experience
      : section === "projects"
        ? data.projects
        : section === "education"
          ? data.education
          : null;
  return entries?.[index]?.bullets?.[bullet_index] ?? null;
}

/** Same normalization + sha256[:16] as backend bullet_classify.content_hash. */
export async function contentHash16(text: string): Promise<string> {
  const normalized = text.split(/\s+/).filter(Boolean).join(" ");
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(normalized),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

/**
 * Which findings' own text has drifted since the report. Per-op
 * expected_content_hash makes applies safe server-side regardless; this is
 * the client-side mirror so a stale REPORT only locks the findings whose
 * bullets actually changed, instead of the whole page.
 */
export async function staleFindingIds<
  T extends {
    id: string;
    content_hash?: string | null;
    location: { section: string; index?: number | null; bullet_index?: number | null };
  },
>(findings: T[], data: ResumeData): Promise<Set<string>> {
  const stale = new Set<string>();
  await Promise.all(
    findings.map(async (finding) => {
      if (!finding.content_hash) return;
      const text = textAtLocation(data, finding);
      if (text == null || (await contentHash16(text)) !== finding.content_hash) {
        stale.add(finding.id);
      }
    }),
  );
  return stale;
}
