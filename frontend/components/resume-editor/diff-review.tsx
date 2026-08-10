"use client";

import { SpellCheck, Undo2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { resumeDataSchema } from "@/lib/resume-schema";
import type { CoherenceFlag, ResumeData, ResumeDiffHunk } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Review-mode overlay for the tailored-resume studio (design §4.5).
 *
 * Reads the backend's structural base→tailored diff and renders it beside the
 * ordinary editor — an OVERLAY, never a fork: the section editors below stay
 * live, and a revert is just an inverse edit written into the studio's working
 * copy, so the studio's own Save is what snapshots the ResumeVersion. No new
 * undo machinery, no second write path.
 */

const PROVENANCE_LABELS: Record<ResumeDiffHunk["provenance"], string> = {
  kb_auto: "KB auto",
  user: "You",
  llm: "AI",
};

const PROVENANCE_STYLES: Record<ResumeDiffHunk["provenance"], string> = {
  kb_auto: "border-primary/40 text-primary bg-primary/10",
  user: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  llm: "border-border bg-muted text-muted-foreground",
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

const SECTION_LABELS: Record<string, string> = {
  summary: "Summary",
  contact: "Contact",
  skills: "Skills",
  experience: "Experience",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
  extra_sections: "Extra sections",
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

const KIND_LABELS: Record<ResumeDiffHunk["kind"], string> = {
  summary_changed: "Summary rewritten",
  contact_changed: "Contact details changed",
  bullet_added: "Bullet added",
  bullet_removed: "Bullet removed",
  bullet_edited: "Bullet reworded",
  entry_added: "Entry added",
  entry_removed: "Entry removed",
  entry_enabled: "Entry unhidden",
  entry_disabled: "Entry hidden",
  skills_group_changed: "Skills group changed",
  extra_section_added: "Section added",
  extra_section_removed: "Section removed",
  extra_section_changed: "Section changed",
  extra_section_enabled: "Section unhidden",
  extra_section_disabled: "Section hidden",
};

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
function sideText(side: unknown): string {
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

/** Bullets live on the entry; `hunk.index` is the ENTRY index and the bullet's
 *  own position is not in the hunk, so added/edited bullets are matched by text. */
function revertEntryBullet(doc: Loose, hunk: ResumeDiffHunk): boolean {
  const list = asList(doc, hunk.section);
  if (!list || hunk.index === null) return false;
  const entry = list[hunk.index];
  if (!isRecord(entry)) return false;
  const bullets = Array.isArray(entry.bullets) ? [...entry.bullets] : [];
  if (hunk.kind === "bullet_added") {
    const at = bullets.indexOf(hunk.after);
    if (at < 0) return false;
    bullets.splice(at, 1);
  } else if (hunk.kind === "bullet_removed") {
    bullets.push(hunk.before);
  } else {
    const at = bullets.indexOf(hunk.after);
    if (at < 0) return false;
    bullets[at] = hunk.before;
  }
  entry.bullets = bullets;
  return true;
}

/** Certifications are a flat top-level list, so their bullet_* hunks carry the
 *  ITEM index — reverting by position, not by text. */
function revertCertification(doc: Loose, hunk: ResumeDiffHunk): boolean {
  const list = asList(doc, "certifications");
  if (!list || hunk.index === null) return false;
  const next = [...list];
  if (hunk.kind === "bullet_added") {
    if (hunk.index >= next.length) return false;
    next.splice(hunk.index, 1);
  } else if (hunk.kind === "bullet_removed") {
    next.splice(Math.min(hunk.index, next.length), 0, hunk.before);
  } else {
    if (hunk.index >= next.length) return false;
    next[hunk.index] = hunk.before;
  }
  doc.certifications = next;
  return true;
}

function revertIndexedList(
  doc: Loose,
  section: string,
  hunk: ResumeDiffHunk,
  added: boolean,
  removed: boolean,
): boolean {
  const list = asList(doc, section);
  if (!list || hunk.index === null) return false;
  const next = [...list];
  if (added) {
    if (hunk.index >= next.length) return false;
    next.splice(hunk.index, 1);
  } else if (removed) {
    next.splice(Math.min(hunk.index, next.length), 0, hunk.before);
  } else {
    if (hunk.index >= next.length) return false;
    next[hunk.index] = hunk.before;
  }
  doc[section] = next;
  return true;
}

/** Extra sections are keyed, not positional — match on `key` so a reordering
 *  tailor op can't make a revert overwrite the wrong section. */
function revertExtraSection(doc: Loose, hunk: ResumeDiffHunk): boolean {
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
    next.splice(Math.min(hunk.index ?? next.length, next.length), 0, hunk.before);
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
 */
export function revertHunk(
  data: ResumeData,
  hunk: ResumeDiffHunk,
): ResumeData | null {
  const doc = cloneLoose(data);
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
      );
      break;
    case "bullet_added":
    case "bullet_removed":
    case "bullet_edited":
      ok =
        hunk.section === "certifications"
          ? revertCertification(doc, hunk)
          : revertEntryBullet(doc, hunk);
      break;
    case "entry_added":
      ok = revertIndexedList(doc, hunk.section, hunk, true, false);
      break;
    case "entry_removed":
      ok = revertIndexedList(doc, hunk.section, hunk, false, true);
      break;
    case "entry_enabled":
    case "entry_disabled":
      ok = revertIndexedList(doc, hunk.section, hunk, false, false);
      break;
    default:
      ok = revertExtraSection(doc, hunk);
      break;
  }
  if (!ok) return null;
  const parsed = resumeDataSchema.safeParse(doc);
  return parsed.success ? parsed.data : null;
}

/**
 * Apply one coherence proposal into the working copy (design §4.4): replace the
 * flagged text — located by exact match on the locus's `after` needle — with the
 * proposal. Same contract as revertHunk: a locus that no longer matches the
 * draft returns null instead of writing something arbitrary.
 */
export function applyCoherenceProposal(
  data: ResumeData,
  flag: CoherenceFlag,
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
  }
  if (!ok) return null;
  const parsed = resumeDataSchema.safeParse(doc);
  return parsed.success ? parsed.data : null;
}

// --- UI ----------------------------------------------------------------------

function ProvenanceChip({ value }: { value: ResumeDiffHunk["provenance"] }) {
  return (
    <Badge
      variant="outline"
      className={cn("shrink-0 font-normal", PROVENANCE_STYLES[value])}
      title={
        value === "kb_auto"
          ? "Applied from your own library/Career KB evidence"
          : value === "user"
            ? "Came from a gap resolution you made"
            : "Wording the tailoring model chose"
      }
    >
      {PROVENANCE_LABELS[value]}
    </Badge>
  );
}

function HunkRow({
  hunk,
  reverted,
  onRevert,
}: {
  hunk: ResumeDiffHunk;
  reverted: boolean;
  onRevert: () => void;
}) {
  const before = sideText(hunk.before);
  const after = sideText(hunk.after);
  return (
    <li className="flex flex-wrap items-start gap-2 py-1.5">
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium">{KIND_LABELS[hunk.kind]}</span>
          <ProvenanceChip value={hunk.provenance} />
          {reverted && (
            <span className="text-muted-foreground text-[10px]">
              reverted — unsaved
            </span>
          )}
        </div>
        {before && (
          <p className="text-muted-foreground text-xs line-through">{before}</p>
        )}
        {after && <p className="text-foreground/90 text-xs">{after}</p>}
      </div>
      <Button
        variant="ghost"
        size="xs"
        className="shrink-0"
        disabled={reverted}
        onClick={onRevert}
      >
        <Undo2 /> Revert
      </Button>
    </li>
  );
}

const ISSUE_LABELS: Record<CoherenceFlag["issue"], string> = {
  fragment: "Reads as a fragment",
  tense: "Tense mismatch",
  summary_mismatch: "Summary out of sync",
  dangling: "Dangling reference",
};

export function coherenceFlagKey(flag: CoherenceFlag, position: number): string {
  return `${position}:${flag.issue}:${flag.locus.section ?? ""}:${flag.locus.index ?? ""}`;
}

export interface CoherenceState {
  /** A check has completed for the current saved version. */
  checked: boolean;
  loading: boolean;
  flags: CoherenceFlag[];
  /** `coherenceFlagKey`s already applied into the working copy. */
  appliedKeys: Set<string>;
}

function CoherenceFlags({
  coherence,
  onApply,
}: {
  coherence: CoherenceState;
  onApply: (flag: CoherenceFlag, key: string) => void;
}) {
  if (coherence.flags.length === 0) {
    return (
      <p className="text-muted-foreground text-xs">
        Coherence check found nothing to flag.
      </p>
    );
  }
  return (
    <ul className="divide-y">
      {coherence.flags.map((flag, position) => {
        const key = coherenceFlagKey(flag, position);
        const applied = coherence.appliedKeys.has(key);
        return (
          <li key={key} className="flex items-start gap-2 p-2 text-sm">
            <Badge variant="outline" className="shrink-0">
              {ISSUE_LABELS[flag.issue]}
            </Badge>
            <div className="min-w-0 flex-1 space-y-0.5">
              {flag.locus.after && (
                <p className="text-muted-foreground truncate text-xs line-through">
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

export function DiffReviewPanel({
  hunks,
  revertedKeys,
  dirty,
  onRevert,
  coherence,
  onCheckCoherence,
  onApplyProposal,
}: {
  hunks: ResumeDiffHunk[];
  /** `hunkKey`s already reverted in the working copy but not yet saved. */
  revertedKeys: Set<string>;
  /** The working copy differs from the saved one, so the diff below is stale. */
  dirty: boolean;
  onRevert: (hunk: ResumeDiffHunk, key: string) => void;
  coherence?: CoherenceState;
  onCheckCoherence?: () => void;
  onApplyProposal?: (flag: CoherenceFlag, key: string) => void;
}) {
  if (hunks.length === 0) {
    return (
      <div className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
        No differences from your base resume.
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
    <section className="space-y-2 rounded-lg border bg-muted/20 p-3">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-medium">
          {hunks.length} {hunks.length === 1 ? "change" : "changes"} from your
          base resume
        </h2>
        <div className="ml-auto flex items-center gap-1">
          <ProvenanceChip value="kb_auto" />
          <ProvenanceChip value="user" />
          <ProvenanceChip value="llm" />
          {/* Design §4.4 trigger: offer the lint only when deterministic
              injections happened — pure-AI drafts were written in one pass. */}
          {onCheckCoherence &&
            coherence &&
            hunks.some((hunk) => hunk.provenance !== "llm") && (
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
                    ? "Re-check coherence"
                    : "Check coherence"}
              </Button>
            )}
        </div>
      </header>
      {dirty && (
        <p className="text-muted-foreground text-xs">
          This list describes the last saved version. Save to refresh it.
        </p>
      )}
      {coherence?.checked && !coherence.loading && onApplyProposal && (
        <CoherenceFlags coherence={coherence} onApply={onApplyProposal} />
      )}
      {groups.map((group) => (
        <div key={group.section}>
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {group.label}
          </p>
          <ul className="divide-y">
            {group.items.map(({ hunk, key }) => (
              <HunkRow
                key={key}
                hunk={hunk}
                reverted={revertedKeys.has(key)}
                onRevert={() => onRevert(hunk, key)}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
