/**
 * Pure helpers for the health report page. Keep this file free of React so
 * Node's type-stripped test runner can import it.
 *
 * LEVEL_VALUES is duplicated in health-zones.ts (the designated Python
 * mirror) — both must stay in lockstep with health_score.LEVEL_VALUES.
 */

import type { ResumeData, WordingBody, WordingRead } from "./types";

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

export const CONTENT_CHANGED_PREFIX = "content changed since analysis";

export const STALE_APPLY_HINT = "This text changed. Check again before applying.";

export const CONTENT_CHANGED_HINT = "This text changed. Check again for new suggestions.";

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
 * The dispute endpoint's own sentences (backend/app/services/health_disputes.py OVERRIDDEN and
 * UNREADABLE), matched to tell its failures apart, never shown from the error itself. Pinned equal
 * to the Python by test_frontend_health_report.py.
 */
export const DISPUTE_DETAIL = {
  overridden: "You set this rating yourself. Set it back to automatic first.",
  unreadable: "Couldn't re-read this bullet. Try again.",
} as const;

/** Which words a failed dispute gets on its card: the two 409s differ only by `detail`. */
export function disputeFailure(err: {
  status?: number;
  message?: string;
}): "changed" | "overridden" | "failed" {
  if (isContentChangedError(err)) return "changed";
  if (err.status === 409 && err.message === DISPUTE_DETAIL.overridden) return "overridden";
  return "failed";
}

/** A dispute moved the rating or the question: the report is out of date and runs again. */
export function disputeChangedRating(result: {
  before: { level: string; question: string | null };
  after: { level: string; question: string | null };
}): boolean {
  return (
    result.before.level !== result.after.level ||
    result.before.question !== result.after.question
  );
}

type Rated = {
  type: string;
  content_hash?: string | null;
  classification_level?: string | null;
};

const isOpen = (f: { type: string }) => f.type === "ask" || f.type === "fix";
/** A finding that rates its text (a bullet, the summary). The summary's years check (C2) carries
 *  the summary's hash too, but rates nothing, so it is not one. */
const ratesText = (f: Rated) => Boolean(f.content_hash && f.classification_level);

/** Some ask or fix in `findings` still rates the text with this hash. */
export function hasOpenRating(findings: Rated[], hash: string): boolean {
  return findings.some((f) => isOpen(f) && ratesText(f) && f.content_hash === hash);
}

type Where = { section: string; index?: number | null; bullet_index?: number | null };

/**
 * The asks and fixes a re-run settled. One that rates text stays open while any open ask or fix
 * rates that text, wherever it sits (a dispute or an override that changes the question gives it a
 * new id; a deleted bullet moves the ones below it), and while its place holds an open ask or fix on
 * text the prior report never had (an applied rewrite that is still flagged). A bullet that only
 * moved keeps a hash the prior report had, so it never holds another place open. One that rates no
 * text (an employment gap, the summary's years check) shares its location with others, so it keeps
 * the id test.
 */
export function resolvedFindings<T extends Rated & { id: string; location: Where }>(
  prior: T[],
  next: (Rated & { id: string; location: Where })[],
): T[] {
  const nextIds = new Set(next.map((f) => f.id));
  const priorHashes = new Set(prior.map((f) => f.content_hash).filter(Boolean));
  const where = (f: { location: Where }) =>
    JSON.stringify([f.location.section, f.location.index ?? null, f.location.bullet_index ?? null]);
  const rewrittenOpen = new Set(
    next
      .filter((f) => isOpen(f) && ratesText(f) && !priorHashes.has(f.content_hash))
      .map(where),
  );
  return prior.filter(
    (f) =>
      isOpen(f) &&
      (ratesText(f)
        ? !hasOpenRating(next, f.content_hash!) && !rewrittenOpen.has(where(f))
        : !nextIds.has(f.id)),
  );
}

/**
 * "Fixed this session" across re-runs (planner decision: the session is the page's). The entries
 * kept so far and a re-run's newly fixed ones merge by id (a newer entry replaces an older one), and
 * an entry whose finding is open again in `next` leaves: rated text an open ask or fix rates again,
 * or, for one that rates no text, its id back among the open findings.
 */
export function mergeResolved<T extends Rated & { id: string }>(
  kept: T[],
  fresh: T[],
  next: (Rated & { id: string })[],
): T[] {
  const openIds = new Set(next.filter(isOpen).map((f) => f.id));
  const reopened = (f: T) => (ratesText(f) ? hasOpenRating(next, f.content_hash!) : openIds.has(f.id));
  const byId = new Map<string, T>();
  for (const f of [...kept, ...fresh]) byId.set(f.id, f);
  return [...byId.values()].filter((f) => !reopened(f));
}

const samePlace = (a: Where, b: Where) =>
  a.section === b.section &&
  (a.index ?? null) === (b.index ?? null) &&
  (a.bullet_index ?? null) === (b.bullet_index ?? null);

/**
 * The tab a dispute's re-run moves the disputed bullet to, or null when it stays put (or left the
 * report). The bullet is the open ask or fix with the disputed text AT the disputed place, before and
 * after: "no number exists" turns a number question into a detail question, and the page opens the
 * detail tab before it adopts the report, so the new card mounts in the open panel on its reply.
 */
export function disputeTabMove<T extends Actionable & Rated & { location: Where }>(
  prior: T[],
  next: T[],
  hash: string,
  where: Where,
): ActionTab | null {
  const at = (list: T[]) =>
    list.find((f) => isOpen(f) && f.content_hash === hash && samePlace(f.location, where));
  const before = at(prior);
  const after = at(next);
  if (!before || !after) return null;
  const from = actionTabOf(before);
  const to = actionTabOf(after);
  return from && to && from !== to ? to : null;
}

/**
 * The dispute a Fixed entry carries: only one whose own re-run lifted the bullet out of the report
 * (`lifted`, recorded by the page). A reply left from an earlier dispute that moved nothing never
 * rides on a bullet the user later fixed by hand.
 */
export function liftedDispute<D>(
  finding: { content_hash?: string | null },
  lifted: ReadonlySet<string>,
  disputes: Record<string, D>,
): D | undefined {
  const hash = finding.content_hash;
  return hash && lifted.has(hash) ? disputes[hash] : undefined;
}

type GateLike = { tier: string; status: string };

const problems = (n: number, tier: string) => `${n} ${tier} ${n === 1 ? "problem" : "problems"}`;

/**
 * "Score limited to 54 by 1 must-fix problem" when failed checks cap the score, naming the real count and
 * tier (`health_score.gate_cap_tier`: one failed must-fix check, or two serious ones, cap at 54; one serious
 * check at 69). Null when nothing capped the score, and when the server sent no `score_breakdown`.
 */
export function scoreCompositionLine(
  score: number,
  breakdown: ScoreBreakdown | null | undefined,
  gates: readonly GateLike[] = [],
): string | null {
  if (!breakdown?.capped_by) return null;
  const failed = gates.filter((g) => g.status === "fail");
  const fatal = failed.filter((g) => g.tier === "fatal").length;
  const serious = failed.filter((g) => g.tier === "serious").length;
  if (breakdown.capped_by === "fatal" && fatal > 0) {
    return `Score limited to ${score} by ${problems(fatal, "must-fix")}`;
  }
  if (serious > 0) return `Score limited to ${score} by ${problems(serious, "serious")}`;
  return `Score limited to ${score} by a failed check`;
}

/**
 * The report's counts with the checks counted by tier. "Must fix" is the fatal tier only, and only a check
 * that failed (`status === "fail"`: a waived or unchecked one fixes nothing), so the chips, the summary, the
 * studio's health link and "left to fix" all say one number. The server's `counts.gate` counts every failed
 * check, serious ones too; it is replaced here, never shown.
 */
export function healthCounts(report: {
  counts?: Record<string, number>;
  gates?: readonly GateLike[];
}): Record<string, number> {
  const failed = (report.gates ?? []).filter((g) => g.status === "fail");
  return {
    ...report.counts,
    gate: failed.filter((g) => g.tier === "fatal").length,
    serious: failed.filter((g) => g.tier === "serious").length,
  };
}

/** Everything still asking for work: failed checks, fixes and questions (never notes). */
export function leftToFix(counts: Record<string, number>, findingsLeft: number): number {
  return (counts.gate ?? 0) + (counts.serious ?? 0) + findingsLeft;
}

/** The toast after a check: never a grade the rail says it can't give. */
export function checkDoneWords(report: { grade: string; insufficient_evidence?: boolean }): string {
  return reportInsufficientEvidence(report)
    ? "Check done. Too little to grade yet."
    : `Check done. Grade ${report.grade}.`;
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

export function groupPoints(
  findings: { level?: number | null; gain?: number | null }[],
  nScoreable: number | null | undefined,
): number {
  return findings.reduce((sum, finding) => {
    if (finding.gain != null) return sum + finding.gain;
    return sum + (potentialPoints(levelNameOf(finding), nScoreable) ?? 0);
  }, 0);
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
  "skills.undemonstrated": "Skill not shown in any bullet",
  "skills.trailing_punct": "Extra punctuation after a skill",
  "certifications.trailing_punct": "Extra punctuation after a certification",
  "skills.duplicate_across_groups": "Skill in more than one group",
  "certifications.duplicate": "Certification listed twice",
  "skills.sentence_like": "Skill reads like a sentence",
  "bullet.too_long": "Bullet is too long",
  "bullet.too_short": "Bullet is too short",
  "entry.too_many_bullets": "Too many bullets",
  "summary.missing": "No summary",
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

export const METRIC_ASK_NEEDLE = "What number measures this";

export function isMetricAsk(finding: { ask_kind?: string | null; question?: string | null }): boolean {
  return finding.ask_kind ? finding.ask_kind === "measure" : (finding.question ?? "").includes(METRIC_ASK_NEEDLE);
}

export function nextGradeLine(report: { next_grade?: { grade: string; points: number } | null }): string | null {
  const next = report.next_grade;
  return next ? `${next.points} ${next.points === 1 ? "point" : "points"} to ${next.grade}` : null;
}

/** The grade bands' floors, lowest first: `health_score.GRADE_BANDS` (below 40 is F). */
export const GRADE_FLOORS = [40, 55, 70, 85] as const;

/**
 * How far the score is from its band's floor to the next band's (0 to 1), for the summary band's bar.
 * Null when there is no next grade to reach (an A, or a score a failed check caps).
 */
export function nextGradeProgress(report: {
  score: number;
  next_grade?: { grade: string; points: number } | null;
}): number | null {
  const next = report.next_grade;
  if (!next) return null;
  const target = report.score + next.points;
  const floor = Math.max(0, ...GRADE_FLOORS.filter((f) => f <= report.score));
  if (target <= floor) return null;
  return Math.min(1, Math.max(0, (report.score - floor) / (target - floor)));
}

/** "Checked 2 minutes ago · Version 28": the header's stamp (`ago` is the relative time). */
export function checkedWords(ago: string, version: number | null | undefined): string {
  return version != null ? `Checked ${ago} · Version ${version}` : `Checked ${ago}`;
}

/** The report's flag for a resume with no number in any scored bullet: the summary band's callout. */
export const NO_NUMBERS_RULE = "evidence.no_numbers";

/** The report's tabs, one per kind of action, then what is done. */
export type HealthTab = "number" | "detail" | "reword" | "shorten" | "notes" | "done";
export type ActionTab = Exclude<HealthTab, "done">;

export const HEALTH_TABS: { id: HealthTab; label: string }[] = [
  { id: "number", label: "Needs a number" },
  { id: "detail", label: "Needs detail" },
  { id: "reword", label: "Reword" },
  { id: "shorten", label: "Shorten" },
  { id: "notes", label: "Notes" },
  { id: "done", label: "Done" },
];

const ACTION_TABS: ActionTab[] = ["number", "detail", "reword", "shorten", "notes"];

/** `?tab=` as a tab, or null for anything else (no param, an old or mistyped value). */
export function parseHealthTab(raw: string | null | undefined): HealthTab | null {
  return HEALTH_TABS.find((t) => t.id === raw)?.id ?? null;
}

type Actionable = {
  type: string;
  ask_kind?: string | null;
  question?: string | null;
  rule?: string;
};

/**
 * The tab a finding is acted on in: a number question, any other question, a rewrite, a too-long
 * bullet, or any other note. Null for a check (the banner above the tabs) and for "No numbers
 * anywhere" (the summary band's callout).
 */
export function actionTabOf(finding: Actionable): ActionTab | null {
  if (finding.type === "ask") return isMetricAsk(finding) ? "number" : "detail";
  if (finding.type === "fix") return "reword";
  if (finding.type === "note") {
    if (finding.rule === NO_NUMBERS_RULE) return null;
    return finding.rule === "bullet.too_long" ? "shorten" : "notes";
  }
  return null;
}

/** Every finding in its tab, in report order. */
export function findingsByTab<T extends Actionable>(findings: T[]): Record<ActionTab, T[]> {
  const tabs: Record<ActionTab, T[]> = { number: [], detail: [], reword: [], shorten: [], notes: [] };
  for (const finding of findings) {
    const tab = actionTabOf(finding);
    if (tab) tabs[tab].push(finding);
  }
  return tabs;
}

/**
 * The tab to open on: the one whose findings would gain the most points, the earlier tab on a tie.
 * With no gain anywhere, the first tab with anything in it; with nothing at all, Notes (it always
 * holds the Wording group and its Edit word list).
 */
export function defaultHealthTab<T extends Actionable & { gain?: number | null }>(findings: T[]): ActionTab {
  const tabs = findingsByTab(findings);
  let pick: ActionTab | null = null;
  let best = 0;
  for (const tab of ACTION_TABS) {
    const gain = tabs[tab].reduce((sum, f) => sum + (f.gain ?? 0), 0);
    if (gain > best) {
      best = gain;
      pick = tab;
    }
  }
  return pick ?? ACTION_TABS.find((tab) => tabs[tab].length > 0) ?? "notes";
}

export type RuleGroup<T> = { key: string; title: string; findings: T[] };

/**
 * A tab's rows grouped by the rule they break, first appearance first, so each rule is stated once
 * in its group's header. A finding with a detector id groups by it (titled from RULE_TITLES); a
 * question or a rewrite has none, and groups by its issue sentence, which is the rule's own words.
 */
export function ruleGroups<T extends { rule?: string; issue: string }>(findings: T[]): RuleGroup<T>[] {
  const order: string[] = [];
  const buckets = new Map<string, T[]>();
  for (const finding of findings) {
    const key = finding.rule ?? finding.issue;
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = [];
      buckets.set(key, bucket);
      order.push(key);
    }
    bucket.push(finding);
  }
  return order.map((key) => {
    const list = buckets.get(key)!;
    const rule = list[0].rule;
    return { key, title: (rule && RULE_TITLES[rule]) || list[0].issue, findings: list };
  });
}

/** The skill group a listed skill sits in ("Languages"), for the unscored-skills table. */
export function skillGroupOf(data: ResumeData | null | undefined, skill: string): string | null {
  const group = data?.skills?.find((g) => g.items.includes(skill));
  return group ? group.category || null : null;
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
  // "rows" stays a unit id (an answer saved with it still composes) but is no
  // longer offered: engineer shorthand.
  { id: "users", label: "users" },
  { id: "percent", label: "%" },
  { id: "hours", label: "hours saved" },
  { id: "minutes", label: "minutes saved" },
  { id: "dollars", label: "$" },
  { id: "other", label: "Other" },
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
      // The rating a bullet entered at is the scorer's key: never printed.
      const n = list.length;
      clauses.push(`${n} new ${n === 1 ? "bullet" : "bullets"} in ${titleFor(key)}`);
    }
  }
  if (resolved.length > 0) {
    clauses.push(
      `${resolved.length} ${resolved.length === 1 ? "issue" : "issues"} fixed`,
    );
  }
  if (reclass > 0) {
    clauses.push(
      `${reclass} ${reclass === 1 ? "rating" : "ratings"} changed`,
    );
  }
  if (clauses.length === 0 || clauses.length > 3) return null;
  return clauses.map((clause) => `${clause}.`).join(" ");
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

/**
 * The one write behind every health Apply: the summary, or one bullet, replaced by `value`. With a
 * `hash`, the server refuses it (409) when the text changed since the check.
 */
export function bulletEditOp(
  location: { section: string; index?: number | null; bullet_index?: number | null },
  value: string,
  hash?: string | null,
): LintEditOp {
  const guard = hash != null ? { expected_content_hash: hash } : {};
  const { section, index, bullet_index } = location;
  return section === "summary"
    ? { kind: "replace_summary", value, ...guard }
    : { kind: "replace_bullet", section, index, bullet_index, value, ...guard };
}

// --- Wording: spelling and grammar slips, clichés and filler (zero score) ----------------------

/** A wording note: `language.cliche`, `language.filler` or `language.slip`. */
export function isWordingRule(rule: string | undefined): boolean {
  return rule != null && rule.startsWith("language.");
}

/** The Wording checklist's notes, and the rest for the rule table. */
export function splitWordingNotes<T extends { rule?: string }>(notes: T[]): { wording: T[]; other: T[] } {
  const wording: T[] = [];
  const other: T[] = [];
  for (const note of notes) (isWordingRule(note.rule) ? wording : other).push(note);
  return { wording, other };
}

/**
 * A slip's fix, read from its issue sentence (resume_lint.py `_slip_notes`: "'<span>' looks like a
 * slip: '<fix>'."). The span is the note's `subject`, so an apostrophe in either one is not a
 * delimiter. Null when the sentence is not that one.
 */
export function slipFix(note: { subject?: string; issue: string }): string | null {
  if (!note.subject) return null;
  const head = `'${note.subject}' looks like a slip: '`;
  if (!note.issue.startsWith(head) || !note.issue.endsWith("'.")) return null;
  return note.issue.slice(head.length, -2) || null;
}

/**
 * The hash-guarded edit that applies a wording note's `suggestion` (the backend's whole edited text,
 * set only when the rewrite guards accept it). Null when there is nothing to apply here: no
 * suggestion, no hash, or an Other section, which has no bullet edit op (its wording is copy-only).
 */
export function wordingEditOp(note: {
  location: { section: string; index?: number | null; bullet_index?: number | null };
  suggestion?: string | null;
  content_hash?: string | null;
}): LintEditOp | null {
  if (note.suggestion == null || !note.content_hash || note.location.section.startsWith("extra:")) return null;
  return bulletEditOp(note.location, note.suggestion, note.content_hash);
}

/** health_wording.MAX_CHARS and MAX_ENTRIES (pinned equal by test_frontend_health_report.py). */
export const WORD_MAX_CHARS = 40;
export const WORD_LIST_MAX = 200;

/** As health_wording.normalize: trimmed, inner whitespace collapsed, lower-cased. */
export function normalizeWord(raw: string): string {
  return raw.trim().split(/\s+/).filter(Boolean).join(" ").toLowerCase();
}

/** `list` with `raw` added, or why it can't be: the backend's limits, said before the Save. */
export function addWord(list: string[], raw: string): { list: string[] } | { error: string } {
  const word = normalizeWord(raw);
  if (!word) return { error: "Type a word or phrase." };
  if (word.length > WORD_MAX_CHARS) return { error: `Keep it to ${WORD_MAX_CHARS} characters or fewer.` };
  if (list.includes(word)) return { error: "That's already on this list." };
  if (list.length >= WORD_LIST_MAX) return { error: `This list is full (${WORD_LIST_MAX}). Remove one first.` };
  return { list: [...list, word] };
}

/** `list` with its add field's text committed, as Save sends it: a blank field adds nothing. */
export function withDraft(list: string[], draft: string): { list: string[] } | { error: string } {
  return normalizeWord(draft) ? addWord(list, draft) : { list };
}

/** Never flag can hold this subject (Ignore is offered). */
export function canIgnore(subject: string | undefined): subject is string {
  const word = normalizeWord(subject ?? "");
  return word.length > 0 && word.length <= WORD_MAX_CHARS;
}

/** The PUT /wording body with `subject` on Never flag: the whole current lists, as the PUT wants. */
export function withIgnored(wording: WordingRead, subject: string): WordingBody {
  const word = normalizeWord(subject);
  return {
    cliche: wording.cliche,
    filler: wording.filler,
    ignored: wording.ignored.includes(word) ? wording.ignored : [...wording.ignored, word],
  };
}

// --- The question pass: every ask on one page, answered in one go --------------------------------

/** "2 of 6 answered". A skipped row still counts: Skip lasts this visit, so the total is every row. */
export function passProgress(rows: { answered: boolean; skipped: boolean }[]): {
  answered: number;
  total: number;
  words: string;
} {
  const answered = rows.filter((row) => row.answered && !row.skipped).length;
  const total = rows.length;
  return { answered, total, words: `${answered} of ${total} answered` };
}

/** The pass's primary button: "Write 3 new versions" ("Write new versions" with none to write). */
export function writeVersionsLabel(n: number): string {
  if (n === 0) return "Write new versions";
  return `Write ${n} new ${n === 1 ? "version" : "versions"}`;
}

/**
 * Accept all shown: every accepted row as ONE `/edits` call (one transaction, one new version), each
 * op guarded by its bullet's hash so a bullet that changed since the check refuses the batch (409).
 */
export function batchEditOps(
  rows: {
    finding: {
      location: { section: string; index?: number | null; bullet_index?: number | null };
      content_hash?: string | null;
    };
    text: string;
  }[],
): LintEditOp[] {
  return rows.map((row) => bulletEditOp(row.finding.location, row.text, row.finding.content_hash));
}

/** The latest version number in a versions list (null with none): the V0 an undo restores. */
export function latestVersionNumber(versions: { version_number: number }[]): number | null {
  return versions.length === 0 ? null : Math.max(...versions.map((v) => v.version_number));
}

/** Runs `fn` over `items`, at most `limit` at a time (the pass drafts three at once). */
export async function mapPool<T>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next;
      next += 1;
      await fn(items[index], index);
    }
  }
  const n = Math.min(limit, items.length);
  await Promise.all(Array.from({ length: n }, () => worker()));
}

export type PassOutcome = { points: number; fixed: number; notRight: number; skipped: number };

/**
 * What a pass did, from the report it started on and the check it closes with: the score change,
 * the pass's own rows the check now calls fixed (`resolvedFindings`; a row the user marked not right
 * counts there instead), and the rows marked not right or skipped.
 */
export function passOutcome<T extends Rated & { id: string; location: Where }>(
  prior: { score: number; findings: T[] },
  next: { score: number; findings: (Rated & { id: string; location: Where })[] },
  passIds: ReadonlySet<string>,
  disputedHashes: ReadonlySet<string>,
  skipped: number,
): PassOutcome {
  const fixed = resolvedFindings(prior.findings, next.findings).filter(
    (f) => passIds.has(f.id) && !(f.content_hash && disputedHashes.has(f.content_hash)),
  ).length;
  return { points: next.score - prior.score, fixed, notRight: disputedHashes.size, skipped };
}

/** The one toast a pass closes with: "+6 points · 3 fixed · 2 not right · 1 skipped". */
export function passOutcomeWords({ points, fixed, notRight, skipped }: PassOutcome): string {
  const score =
    points === 0
      ? "Same score"
      : `${points > 0 ? "+" : ""}${points} ${Math.abs(points) === 1 ? "point" : "points"}`;
  const parts = [score];
  if (fixed > 0) parts.push(`${fixed} fixed`);
  if (notRight > 0) parts.push(`${notRight} not right`);
  if (skipped > 0) parts.push(`${skipped} skipped`);
  return parts.join(" · ");
}

export type BulletContext = { heading: string; dates: string | null; bullets: string[]; active: number };

const dateRange = (...parts: (string | null | undefined)[]) =>
  parts.filter(Boolean).join(" – ") || null;

/**
 * The item an asked bullet sits in, from the resume: its heading, dates and every bullet, with the
 * asked one's index (the pass's context pane). Null when the place no longer holds a bullet.
 */
export function bulletContext(
  data: ResumeData,
  location: { section: string; index?: number | null; bullet_index?: number | null },
): BulletContext | null {
  const { section, index, bullet_index } = location;
  const make = (heading: string, dates: string | null, bullets: string[] | undefined, active: number) =>
    bullets && active >= 0 && active < bullets.length ? { heading, dates, bullets, active } : null;
  if (section === "summary") return data.summary ? make("Summary", null, [data.summary], 0) : null;
  if (bullet_index == null) return null;
  if (section.startsWith("extra:")) {
    const sec = data.extra_sections?.find((s) => s.key === section.slice("extra:".length));
    if (!sec) return null;
    if (sec.type === "bullets") return make(sec.title, null, sec.bullets, bullet_index);
    const entry = index != null ? sec.entries?.[index] : undefined;
    return entry ? make(entry.heading || sec.title, dateRange(entry.date), entry.bullets, bullet_index) : null;
  }
  if (index == null) return null;
  const heading = groupTitle(`${section}:${index}`, data);
  if (section === "experience") {
    const entry = data.experience?.[index];
    return entry ? make(heading, dateRange(entry.start_date, entry.end_date), entry.bullets, bullet_index) : null;
  }
  if (section === "projects") {
    const entry = data.projects?.[index];
    return entry ? make(heading, dateRange(entry.date), entry.bullets, bullet_index) : null;
  }
  if (section === "education") {
    const entry = data.education?.[index];
    return entry
      ? make(heading, dateRange(entry.start_date, entry.end_date ?? entry.graduation_date), entry.bullets, bullet_index)
      : null;
  }
  return null;
}
