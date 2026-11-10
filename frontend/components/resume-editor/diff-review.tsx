"use client";

import { useId } from "react";
import { Redo2, SpellCheck, Undo2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { HunkDiff } from "@/components/resume-editor/hunk-diff";
import { Button } from "@/components/ui/button";
import { ActorChip } from "@/components/visual";
import { resumeDataSchema } from "@/lib/resume-schema";
import { KIND_LABELS, SECTION_LABELS } from "@/lib/resume-diff";
import { serverKey } from "@/lib/studio";
import type {
  CoherenceFlag,
  HealthGate,
  HygieneFlag,
  ResumeData,
  ResumeDiffHunk,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Review-mode overlay for the tailored-resume studio (design §4.5).
 *
 * Reads the backend's structural base→tailored diff and renders it beside the
 * ordinary editor — an OVERLAY, never a fork: the section editors below stay
 * live, and a revert is just an inverse edit written into the studio's working
 * copy, so the studio's own Save is what snapshots the ResumeVersion. A Redo is
 * the revert of that revert (`inverseHunk`), written the same way. No undo
 * stack, no second write path.
 */

// Each provenance as its register chip, for the studio's review mode and the job page's step 3 (one set of words).
// The "llm" entry is never drawn: ProvenanceChip returns null for an llm hunk (an unattributed change), and the
// entry only completes the Record over every provenance.
const PROVENANCE_CHIPS: Record<
  ResumeDiffHunk["provenance"],
  { kind: "careerHistory" | "you" | "ai"; name?: string; title: string }
> = {
  kb_auto: { kind: "careerHistory", name: "From your career history", title: "Taken from your career history" },
  user: { kind: "you", title: "From an answer you gave" },
  llm: { kind: "ai", title: "Wording written by AI" },
};

/**
 * Diff section → the studio surface that edits it, for the count badges.
 * "summary" is a pseudo-tab: the summary textarea sits ABOVE the tab row, so its
 * badge hangs off that label instead of a `TabsTrigger`.
 */
const SECTION_TABS: Record<string, string> = {
  summary: "summary",
  contact: "contact",
  skills: "skills",
  experience: "experience",
  projects: "projects",
  education: "education",
  certifications: "certifications",
  extra_sections: "extra",
};

const SECTION_ORDER = [
  "summary",
  "contact",
  "skills",
  "experience",
  "projects",
  "education",
  "certifications",
  "extra_sections",
];

/** Stable per-hunk identity. The endpoint has no hunk ids, and (kind, section,
 *  index) repeats for several bullets of one entry — so position is part of it. */
export function hunkKey(hunk: ResumeDiffHunk, position: number): string {
  return `${position}:${hunk.kind}:${hunk.section}:${hunk.index ?? ""}`;
}

/** Per-studio-tab change counts, for the badges on the tab row. */
export function sectionChangeCounts(
  hunks: ResumeDiffHunk[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const hunk of hunks) {
    const tab = SECTION_TABS[hunk.section];
    if (!tab) continue;
    counts[tab] = (counts[tab] ?? 0) + 1;
  }
  return counts;
}

// --- readable previews -------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function joinStrings(value: unknown): string {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string").join(", ")
    : "";
}

/** One line describing a hunk side, whatever shape the schema gave it. */
export function sideText(side: unknown): string {
  if (side === null || side === undefined) return "";
  if (typeof side === "string") return side;
  if (Array.isArray(side)) return joinStrings(side);
  if (!isRecord(side)) return String(side);
  if (typeof side.category === "string") {
    const items = joinStrings(side.items);
    return items ? `${side.category}: ${items}` : side.category;
  }
  for (const key of ["name", "heading", "title", "role", "institution"]) {
    const value = side[key];
    if (typeof value === "string" && value.trim()) {
      const company = side.company;
      return key === "role" && typeof company === "string"
        ? `${company} — ${value}`
        : value;
    }
  }
  const parts = Object.entries(side)
    .filter(([, value]) => typeof value === "string" && value.trim())
    .map(([key, value]) => `${key}: ${String(value)}`);
  return parts.join(" · ");
}

// --- revert ------------------------------------------------------------------

type Loose = Record<string, unknown>;

function cloneLoose(data: ResumeData): Loose {
  return JSON.parse(JSON.stringify(data)) as Loose;
}

function asList(doc: Loose, section: string): unknown[] | null {
  const list = doc[section];
  return Array.isArray(list) ? list : null;
}

/** Same content, whatever the key order (the server's and the form's differ). */
const same = (a: unknown, b: unknown) => serverKey(a) === serverKey(b);

const sameKey = (a: unknown, b: unknown) => isRecord(a) && isRecord(b) && a.key === b.key;

/** Where `item` sits in `list`: at `hint` when that is it, else at the first identical item; -1 when nowhere. */
function findSame(list: unknown[], item: unknown, hint: number | null): number {
  if (hint !== null && hint < list.length && same(list[hint], item)) return hint;
  return list.findIndex((other) => same(other, item));
}

/**
 * Where an item put back into `list` goes. An Undo has no `reference` and takes `fallback`. A Redo passes the
 * saved draft's list and where that holds the item (`at`): the item goes before its nearest later neighbour
 * still in `list`, else after its nearest earlier one, else to `at` itself. Its neighbours can be undone and
 * redone in any order and it still lands in its saved place, which an index remembered at the Undo cannot do.
 */
function placeLike(
  list: unknown[],
  reference: unknown[] | null,
  at: number,
  fallback: number,
  alike: (a: unknown, b: unknown) => boolean = same,
): number {
  if (!reference || at < 0) return fallback;
  for (let i = at + 1; i < reference.length; i++) {
    const found = list.findIndex((item) => alike(item, reference[i]));
    if (found >= 0) return found;
  }
  for (let i = at - 1; i >= 0; i--) {
    const found = list.findIndex((item) => alike(item, reference[i]));
    if (found >= 0) return found + 1;
  }
  return Math.min(at, list.length);
}

/** A bullet hunk's own list: its entry's bullets (`hunk.index` is the ENTRY index). */
function entryBullets(doc: Loose, hunk: ResumeDiffHunk): unknown[] | null {
  const list = asList(doc, hunk.section);
  const entry = list && hunk.index !== null ? list[hunk.index] : null;
  if (!isRecord(entry)) return null;
  return Array.isArray(entry.bullets) ? entry.bullets : [];
}

/** Bullets live on the entry; `hunk.index` is the ENTRY index and the bullet's
 *  own position is not in the hunk, so added/edited bullets are matched by text. */
function revertEntryBullet(doc: Loose, hunk: ResumeDiffHunk, saved: Loose | null): boolean {
  const current = entryBullets(doc, hunk);
  if (!current) return false;
  const bullets = [...current];
  if (hunk.kind === "bullet_added") {
    const at = bullets.indexOf(hunk.after);
    if (at < 0) return false;
    bullets.splice(at, 1);
  } else if (hunk.kind === "bullet_removed") {
    const reference = saved && entryBullets(saved, hunk);
    const at = placeLike(bullets, reference, reference ? reference.indexOf(hunk.before) : -1, bullets.length);
    bullets.splice(at, 0, hunk.before);
  } else {
    const at = bullets.indexOf(hunk.after);
    if (at < 0) return false;
    bullets[at] = hunk.before;
  }
  (asList(doc, hunk.section)![hunk.index!] as Loose).bullets = bullets;
  return true;
}

/**
 * Skill groups, entries and certifications: flat lists the hunk indexes (a certification's bullet_* hunk carries
 * the ITEM index). The hunk's item is found by content first, since a sibling undone above it has moved it; an
 * Undo then falls back to the index, as its hunk came from the server and may be shaped differently from the
 * form's copy. A Redo's hunk was read from the draft (`inverseHunk`), so its item is found exactly or not at all.
 */
function revertIndexedList(
  doc: Loose,
  section: string,
  hunk: ResumeDiffHunk,
  added: boolean,
  removed: boolean,
  saved: Loose | null,
): boolean {
  const list = asList(doc, section);
  if (!list || hunk.index === null) return false;
  const next = [...list];
  if (removed) {
    const reference = saved && asList(saved, section);
    const from = reference ? findSame(reference, hunk.before, hunk.index) : -1;
    next.splice(placeLike(next, reference, from, Math.min(hunk.index, next.length)), 0, hunk.before);
  } else {
    let at = findSame(next, hunk.after, hunk.index);
    if (at < 0 && !saved && hunk.index < next.length) at = hunk.index;
    if (at < 0) return false;
    if (added) next.splice(at, 1);
    else next[at] = hunk.before;
  }
  doc[section] = next;
  return true;
}

/** Extra sections are keyed, not positional — match on `key` so a reordering
 *  tailor op can't make a revert overwrite the wrong section. */
function revertExtraSection(doc: Loose, hunk: ResumeDiffHunk, saved: Loose | null): boolean {
  const list = asList(doc, "extra_sections");
  if (!list) return false;
  const next = [...list];
  const source = isRecord(hunk.before) ? hunk.before : hunk.after;
  const key = isRecord(source) ? source.key : undefined;
  if (typeof key !== "string") return false;
  const at = next.findIndex((item) => isRecord(item) && item.key === key);
  if (hunk.kind === "extra_section_added") {
    if (at < 0) return false;
    next.splice(at, 1);
  } else if (hunk.kind === "extra_section_removed") {
    if (at >= 0) return false;
    const reference = saved && asList(saved, "extra_sections");
    const from = reference ? reference.findIndex((item) => sameKey(item, source)) : -1;
    const fallback = Math.min(hunk.index ?? next.length, next.length);
    next.splice(placeLike(next, reference, from, fallback, sameKey), 0, hunk.before);
  } else {
    if (at < 0) return false;
    next[at] = hunk.before;
  }
  doc.extra_sections = next;
  return true;
}

/**
 * The inverse of one hunk, applied to the studio's working copy.
 *
 * Returns null when the change can no longer be located (already reverted, or
 * hand-edited since the diff was computed) or when the result would not validate
 * — the caller surfaces that instead of silently writing a broken document.
 *
 * A Redo is this same function over the Undo's own inverse (`inverseHunk`), with
 * `redoIn` set to the saved draft: what the Redo puts back takes its saved place
 * among its neighbours, and what it takes out again is found exactly or not at all.
 */
export function revertHunk(
  data: ResumeData,
  hunk: ResumeDiffHunk,
  redoIn?: ResumeData,
): ResumeData | null {
  const doc = cloneLoose(data);
  const saved = redoIn ? cloneLoose(redoIn) : null;
  let ok = false;
  switch (hunk.kind) {
    case "summary_changed":
      doc.summary = typeof hunk.before === "string" ? hunk.before : null;
      ok = true;
      break;
    case "contact_changed":
      if (isRecord(hunk.before)) {
        doc.contact = hunk.before;
        ok = true;
      }
      break;
    case "skills_group_changed":
      ok = revertIndexedList(
        doc,
        "skills",
        hunk,
        hunk.before === null,
        hunk.after === null,
        saved,
      );
      break;
    case "bullet_added":
    case "bullet_removed":
    case "bullet_edited":
      ok =
        hunk.section === "certifications"
          ? revertIndexedList(
              doc,
              "certifications",
              hunk,
              hunk.kind === "bullet_added",
              hunk.kind === "bullet_removed",
              saved,
            )
          : revertEntryBullet(doc, hunk, saved);
      break;
    case "entry_added":
      ok = revertIndexedList(doc, hunk.section, hunk, true, false, saved);
      break;
    case "entry_removed":
      ok = revertIndexedList(doc, hunk.section, hunk, false, true, saved);
      break;
    case "entry_enabled":
    case "entry_disabled":
      ok = revertIndexedList(doc, hunk.section, hunk, false, false, saved);
      break;
    default:
      ok = revertExtraSection(doc, hunk, saved);
      break;
  }
  if (!ok) return null;
  const parsed = resumeDataSchema.safeParse(doc);
  return parsed.success ? parsed.data : null;
}

/** The kind that describes a hunk's Undo: what was added is now removed, what was hidden is now shown. */
const INVERSE_KIND: Record<ResumeDiffHunk["kind"], ResumeDiffHunk["kind"]> = {
  summary_changed: "summary_changed",
  contact_changed: "contact_changed",
  skills_group_changed: "skills_group_changed",
  bullet_added: "bullet_removed",
  bullet_removed: "bullet_added",
  bullet_edited: "bullet_edited",
  entry_added: "entry_removed",
  entry_removed: "entry_added",
  entry_enabled: "entry_disabled",
  entry_disabled: "entry_enabled",
  extra_section_added: "extra_section_removed",
  extra_section_removed: "extra_section_added",
  extra_section_changed: "extra_section_changed",
  extra_section_enabled: "extra_section_disabled",
  extra_section_disabled: "extra_section_enabled",
};

/**
 * The hunk that takes an Undo back, read off the draft on both sides of it: `before` is what the draft held
 * (`data`, a hand edit included) and `after` is what the Undo left there (`undone`, the result of
 * `revertHunk(data, hunk)`). `revertHunk` over it with the saved draft is the Redo, so Undo and Redo are one
 * mechanism and a Redo restores the draft's own text, not the saved version's.
 */
export function inverseHunk(
  data: ResumeData,
  undone: ResumeData,
  hunk: ResumeDiffHunk,
): ResumeDiffHunk {
  const kind = INVERSE_KIND[hunk.kind];
  const [pre, post] = [cloneLoose(data), cloneLoose(undone)];
  if (hunk.kind === "summary_changed" || hunk.kind === "contact_changed") {
    return { ...hunk, kind, before: pre[hunk.section] ?? null, after: post[hunk.section] ?? null };
  }
  const inEntry = hunk.kind.startsWith("bullet_") && hunk.section !== "certifications";
  const listOf = (doc: Loose) => (inEntry ? entryBullets(doc, hunk) : asList(doc, hunk.section)) ?? [];
  const [was, now] = [listOf(pre), listOf(post)];
  // An Undo is one edit to one list: the first place the two differ is where it took an item out, put one in or
  // swapped one. Where it changed nothing, the hunk's own index is the place.
  let at = 0;
  while (at < was.length && at < now.length && same(was[at], now[at])) at++;
  if (was.length === now.length && at === was.length) at = hunk.index ?? 0;
  return {
    ...hunk,
    kind,
    index: inEntry ? hunk.index : at,
    before: (now.length <= was.length ? was[at] : null) ?? null,
    after: (now.length >= was.length ? now[at] : null) ?? null,
  };
}

/**
 * The `applyCoherenceProposal` contract needs only a locus + a guaranteed-
 * string proposal — both a `CoherenceFlag` and a `HygieneFlag` whose
 * `proposal` isn't null satisfy that shape. A narrow union rather than `any`,
 * so the compiler still enforces `proposal: string` at every call site.
 */
export type ApplicableCoherenceProposal =
  | CoherenceFlag
  | (HygieneFlag & { proposal: string });

/**
 * Apply one coherence or hygiene proposal into the working copy (design §4.4):
 * replace the flagged text — located by exact match on the locus's `after`
 * needle — with the proposal. Same contract as revertHunk: a locus that no
 * longer matches the draft returns null instead of writing something
 * arbitrary.
 */
export function applyCoherenceProposal(
  data: ResumeData,
  flag: ApplicableCoherenceProposal,
): ResumeData | null {
  const doc = cloneLoose(data);
  const { section, index, after } = flag.locus;
  let ok = false;
  // summary_mismatch applies BY ISSUE: the summary usually has no diff hunk
  // (that's the point of the flag), so there is no needle to match — the
  // proposal, shown verbatim to the user before they click, replaces it.
  if (section === "summary" || flag.issue === "summary_mismatch") {
    doc.summary = flag.proposal;
    ok = true;
  } else if (
    (section === "experience" || section === "projects") &&
    typeof index === "number" &&
    typeof after === "string"
  ) {
    const entries = doc[section];
    const entry = Array.isArray(entries) ? entries[index] : undefined;
    if (isRecord(entry) && Array.isArray(entry.bullets)) {
      const at = entry.bullets.indexOf(after);
      if (at !== -1) {
        entry.bullets[at] = flag.proposal;
        ok = true;
      }
    }
  } else if (section === "certifications" && typeof after === "string") {
    if (Array.isArray(doc.certifications)) {
      const at = doc.certifications.indexOf(after);
      if (at !== -1) {
        doc.certifications[at] = flag.proposal;
        ok = true;
      }
    }
  } else if (section === "skills" && typeof after === "string") {
    const groups = doc.skills;
    if (Array.isArray(groups)) {
      // index is the skills GROUP index when the backend could resolve it;
      // fall back to a scan so a group reorder between check and apply
      // doesn't silently no-op.
      const search = typeof index === "number" ? [groups[index], ...groups] : groups;
      for (const group of search) {
        if (isRecord(group) && Array.isArray(group.items)) {
          const at = group.items.indexOf(after);
          if (at !== -1) {
            group.items[at] = flag.proposal;
            ok = true;
            break;
          }
        }
      }
    }
  }
  if (!ok) return null;
  const parsed = resumeDataSchema.safeParse(doc);
  return parsed.success ? parsed.data : null;
}

// --- UI ----------------------------------------------------------------------

/** Step 3's container pair for each provenance (`tinted`); the studio's review mode draws the plain chip. */
const PROVENANCE_TONE: Record<Exclude<ResumeDiffHunk["provenance"], "llm">, string> = {
  kb_auto: "bg-success-container text-on-success-container",
  user: "bg-primary-container text-on-primary-container",
};

/** One provenance's chip, in the studio's review mode and on the job page's step 3 (`tinted`). */
export function ProvenanceChip({ value, tinted = false }: { value: ResumeDiffHunk["provenance"]; tinted?: boolean }) {
  // "llm" is the server's default for a change it could not attribute
  // (resume_diff.attribute): an edit made here, or a change in the base resume
  // after this copy was made, read as "AI". Unknown says nothing.
  if (value === "llm") return null;
  const { kind, name, title } = PROVENANCE_CHIPS[value];
  return <ActorChip kind={kind} name={name} title={title} className={tinted ? PROVENANCE_TONE[value] : undefined} />;
}

function HunkRow({
  hunk,
  reverted,
  onRevert,
  onRedo,
}: {
  hunk: ResumeDiffHunk;
  reverted: boolean;
  onRevert: () => void;
  onRedo: () => void;
}) {
  const id = useId();
  const before = sideText(hunk.before);
  const after = sideText(hunk.after);
  return (
    <li className="flex flex-wrap items-start gap-2 py-1.5">
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span id={`${id}-kind`} className="text-label-medium">{KIND_LABELS[hunk.kind]}</span>
          <ProvenanceChip value={hunk.provenance} />
          {reverted && (
            <span className="text-muted-foreground text-body-small">
              Undone. Not saved yet.
            </span>
          )}
        </div>
        <div id={`${id}-diff`}>
          <HunkDiff before={before} after={after} className="text-body-small" />
        </div>
      </div>
      {/* One button for both, so focus stays on it when Undo turns into Redo and back. Its name is its word and
          the change's ("Redo Summary rewritten"); the old and new text describe which change that is. */}
      <Button
        id={`${id}-action`}
        variant="ghost"
        size="xs"
        className="shrink-0"
        aria-labelledby={`${id}-action ${id}-kind`}
        aria-describedby={`${id}-diff`}
        onClick={reverted ? onRedo : onRevert}
      >
        {reverted ? (
          <>
            <Redo2 /> Redo
          </>
        ) : (
          <>
            <Undo2 /> Undo
          </>
        )}
      </Button>
    </li>
  );
}

const ISSUE_LABELS: Record<CoherenceFlag["issue"], string> = {
  fragment: "Incomplete sentence",
  tense: "Mixed tenses",
  summary_mismatch: "Summary doesn't match",
  dangling: "Refers to something missing",
};

export function coherenceFlagKey(flag: CoherenceFlag, position: number): string {
  return `${position}:${flag.issue}:${flag.locus.section ?? ""}:${flag.locus.index ?? ""}`;
}

export interface CoherenceState {
  /** A check has completed for the current saved version. */
  checked: boolean;
  loading: boolean;
  flags: CoherenceFlag[];
  /** Deterministic resume_lint findings, scoped to loci the tailoring changed.
   *  Optional so existing call sites built before this group existed still
   *  satisfy the type — absent is treated the same as empty. */
  hygiene?: HygieneFlag[];
  /** Structural gates run against the tailored document. Same optionality
   *  rationale as `hygiene`. */
  gates?: HealthGate[];
  /** `coherenceFlagKey`/`hygieneFlagKey`s already applied into the working copy. */
  appliedKeys: Set<string>;
}

export function hygieneFlagKey(flag: HygieneFlag, position: number): string {
  return `${position}:${flag.rule}:${flag.locus.section ?? ""}:${flag.locus.index ?? ""}`;
}

function CoherenceFlags({
  coherence,
  onApply,
}: {
  coherence: CoherenceState;
  onApply: (flag: CoherenceFlag, key: string) => void;
}) {
  return (
    <ul className="divide-y">
      {coherence.flags.map((flag, position) => {
        const key = coherenceFlagKey(flag, position);
        const applied = coherence.appliedKeys.has(key);
        return (
          <li key={key} className="flex items-start gap-2 p-2 text-body-medium">
            <Badge variant="outline" className="shrink-0">
              {ISSUE_LABELS[flag.issue]}
            </Badge>
            <div className="min-w-0 flex-1 space-y-0.5">
              {flag.locus.after && (
                <p className="text-muted-foreground truncate text-body-small line-through">
                  {flag.locus.after}
                </p>
              )}
              <p className="break-words">{flag.proposal}</p>
            </div>
            <Button
              size="sm"
              variant={applied ? "ghost" : "outline"}
              disabled={applied}
              onClick={() => onApply(flag, key)}
            >
              {applied ? "Applied" : "Apply"}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

/** Gate row for the coherence panel — same accent language as
 *  `resume-health/finding-cards.tsx`'s `FailedGate`, minus the waive
 *  affordance: these gates are read-only status on the tailored document,
 *  not a persisted, waivable health-report gate. */
function GateRow({ gate }: { gate: HealthGate }) {
  const notAssessed = gate.status === "not_assessed";
  const accent = notAssessed
    ? "border-border bg-surface-container-low"
    : gate.tier === "fatal"
      ? "border-destructive/50 bg-destructive/5"
      : "border-border";
  const badgeStyle = notAssessed
    ? "bg-muted text-muted-foreground"
    : gate.tier === "fatal"
      ? "bg-error-container text-on-error-container"
      : "bg-warning-container text-on-warning-container";
  const badgeLabel = notAssessed
    ? "Not checked"
    : gate.tier === "fatal"
      ? "Must fix"
      : "Serious";
  return (
    <div className={cn("rounded-corner-md border px-3 py-2 text-body-medium", accent)}>
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className={cn("shrink-0", badgeStyle)}>
          {badgeLabel}
        </Badge>
        <span className="font-medium">{gate.label}</span>
      </div>
      {gate.detail && (
        <p className="text-muted-foreground mt-1">{gate.detail}</p>
      )}
    </div>
  );
}

function GatesGroup({ gates }: { gates: HealthGate[] }) {
  const nonPassing = gates.filter((gate) => gate.status !== "pass");
  if (nonPassing.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {/* "Checks", not "Must fix": the rows are serious and unchecked ones
          too. "Must fix" is the fatal tier's badge only. */}
      <p className="text-muted-foreground text-title-small">
        Checks
      </p>
      <div className="space-y-1.5">
        {nonPassing.map((gate) => (
          <GateRow key={gate.id} gate={gate} />
        ))}
      </div>
    </div>
  );
}

function HygieneGroup({
  hygiene,
  appliedKeys,
  onApply,
}: {
  hygiene: HygieneFlag[];
  appliedKeys: Set<string>;
  onApply?: (flag: HygieneFlag, key: string) => void;
}) {
  if (hygiene.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-muted-foreground text-title-small">
        Clean-up
      </p>
      <ul className="divide-y">
        {hygiene.map((flag, position) => {
          const key = hygieneFlagKey(flag, position);
          const applied = appliedKeys.has(key);
          return (
            <li key={key} className="flex items-start gap-2 p-2 text-body-medium">
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="break-words">{flag.issue}</p>
                <p className="text-muted-foreground text-body-small">{flag.how}</p>
              </div>
              {flag.proposal !== null && onApply && (
                <Button
                  size="sm"
                  variant={applied ? "ghost" : "outline"}
                  disabled={applied}
                  onClick={() => onApply(flag, key)}
                >
                  {applied ? "Applied" : "Apply"}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * The three post-tailor review groups, most serious first: structural gates,
 * then hygiene (deterministic resume_lint findings), then the LLM coherence
 * flags. Each group renders only when non-empty; if all three are empty a
 * single line replaces three empty headers.
 */
function CoherenceResults({
  coherence,
  onApply,
  onApplyHygiene,
}: {
  coherence: CoherenceState;
  onApply?: (flag: CoherenceFlag, key: string) => void;
  onApplyHygiene?: (flag: HygieneFlag, key: string) => void;
}) {
  const gates = coherence.gates ?? [];
  const hygiene = coherence.hygiene ?? [];
  const nonPassingGates = gates.filter((gate) => gate.status !== "pass");
  const hasAny =
    nonPassingGates.length > 0 ||
    hygiene.length > 0 ||
    coherence.flags.length > 0;
  if (!hasAny) {
    return <p className="text-muted-foreground text-body-small">No issues found.</p>;
  }
  return (
    <div className="space-y-3">
      <GatesGroup gates={gates} />
      <HygieneGroup
        hygiene={hygiene}
        appliedKeys={coherence.appliedKeys}
        onApply={onApplyHygiene}
      />
      {coherence.flags.length > 0 && onApply && (
        <div className="space-y-1.5">
          <p className="text-muted-foreground text-title-small">
            Flow and consistency
          </p>
          <CoherenceFlags coherence={coherence} onApply={onApply} />
        </div>
      )}
    </div>
  );
}

export function DiffReviewPanel({
  hunks,
  revertedKeys,
  dirty,
  onRevert,
  onRedo,
  coherence,
  onCheckCoherence,
  onApplyProposal,
  onApplyHygiene,
}: {
  hunks: ResumeDiffHunk[];
  /** `hunkKey`s undone in the working copy but not yet saved: these rows offer Redo. */
  revertedKeys: { has(key: string): boolean };
  /** The working copy differs from the saved one, so the diff below is stale. */
  dirty: boolean;
  onRevert: (hunk: ResumeDiffHunk, key: string) => void;
  onRedo: (key: string) => void;
  coherence?: CoherenceState;
  onCheckCoherence?: () => void;
  onApplyProposal?: (flag: CoherenceFlag, key: string) => void;
  onApplyHygiene?: (flag: HygieneFlag, key: string) => void;
}) {
  if (hunks.length === 0) {
    return (
      <div className="text-muted-foreground rounded-corner-md border border-dashed p-3 text-body-medium">
        No changes from your base resume.
      </div>
    );
  }
  const groups = SECTION_ORDER.map((section) => ({
    section,
    label: SECTION_LABELS[section] ?? section,
    items: hunks
      .map((hunk, position) => ({ hunk, key: hunkKey(hunk, position) }))
      .filter(({ hunk }) => hunk.section === section),
  })).filter((group) => group.items.length > 0);

  return (
    <section className="space-y-2 rounded-corner-md border p-3">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-title-small">
          {hunks.length} {hunks.length === 1 ? "change" : "changes"} from your
          base resume
        </h2>
        <div className="ml-auto flex items-center gap-1">
          <ProvenanceChip value="kb_auto" />
          <ProvenanceChip value="user" />
          <ProvenanceChip value="llm" />
          {onCheckCoherence && coherence && (
            <Button
              size="sm"
              variant="outline"
              disabled={coherence.loading}
              onClick={onCheckCoherence}
            >
              <SpellCheck aria-hidden />
              {coherence.loading
                ? "Checking…"
                : coherence.checked
                  ? "Check again"
                  : "Check wording"}
            </Button>
          )}
        </div>
      </header>
      {dirty && (
        <p className="text-muted-foreground text-body-small">
          This list describes the last saved version. Save to refresh it.
        </p>
      )}
      {coherence?.checked && !coherence.loading && (
        <CoherenceResults
          coherence={coherence}
          onApply={onApplyProposal}
          onApplyHygiene={onApplyHygiene}
        />
      )}
      {groups.map((group) => (
        <div key={group.section}>
          <p className="text-muted-foreground text-title-small">
            {group.label}
          </p>
          <ul className="divide-y">
            {group.items.map(({ hunk, key }) => (
              <HunkRow
                key={key}
                hunk={hunk}
                reverted={revertedKeys.has(key)}
                onRevert={() => onRevert(hunk, key)}
                onRedo={() => onRedo(key)}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
