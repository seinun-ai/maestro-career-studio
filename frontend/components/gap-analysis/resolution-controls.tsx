"use client";

import { useId, type ReactNode } from "react";
import { Library, Sparkles } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { GapAction, LibraryCandidate, ResumeData } from "@/lib/types";

interface PlacementTargetDisplay {
  index_or_category: string | number;
  label: string;
  /** Display date for experience/project chips (skills have none). */
  date?: string | null;
  /**
   * The most-recent dated entry in its section. Placement here adds little recency
   * gain (the entry is already current), so it's flagged for the user.
   */
  recent?: boolean;
}

/** A concrete place on the base resume where a keyword can be added. */
export type PlacementTarget = PlacementTargetDisplay &
  (
    | {
        section: "skills" | "experience" | "projects";
        section_key?: never;
      }
    | {
        section: "extra";
        /** Stable custom-section identity. */
        section_key: string;
      }
  );

/** What gets persisted in the resolution payload (no display label). */
export type SavedTarget =
  | {
      section: "skills" | "experience" | "projects";
      section_key?: never;
      index_or_category: string | number;
    }
  | {
      section: "extra";
      /** Stable custom-section identity. */
      section_key: string;
      index_or_category: string | number;
    };

export const ACTION_LABELS: Record<GapAction, string> = {
  add_keyword: "Add keyword",
  user_input: "Answer",
  attach_project: "Attach project",
  skip: "Skip",
  enable_entry: "Enable entry",
  port_kb_point: "Use KB evidence",
  cannot_confirm: "I can't confirm this",
};

/** One-line explanation shown wherever the cannot_confirm affordance appears. */
export const CANNOT_CONFIRM_EXPLANATION =
  "Saved so you won't be asked again; never used as evidence.";

/**
 * The actions the segmented control may offer. `enable_entry` and
 * `port_kb_point` are deliberately absent: the server only accepts them with a
 * payload built from a verified library candidate (entry index / approved KB
 * point id / canonical target), so their ONLY affordance is a library chip.
 * Listing them here would reproduce the bug they caused — two blank buttons
 * whose click wiped the gap's stored auto-resolution.
 */
const SEGMENT_ACTIONS: readonly GapAction[] = [
  "add_keyword",
  "user_input",
  "attach_project",
  "skip",
];

const MONTH_NAMES = [
  "jan",
  "feb",
  "mar",
  "apr",
  "may",
  "jun",
  "jul",
  "aug",
  "sep",
  "oct",
  "nov",
  "dec",
];

/**
 * Coarse comparable rank for a free-form resume date ("2023-06", "Jun 2023",
 * "June 2023", "2021"). Present/current → +∞; unparseable/empty → −∞. Only used to
 * find the single most-recent entry, so month-level precision is enough.
 */
function dateSortKey(raw: string | null | undefined): number {
  if (!raw) return Number.NEGATIVE_INFINITY;
  const s = raw.trim().toLowerCase();
  if (!s) return Number.NEGATIVE_INFINITY;
  if (/present|current|now|ongoing/.test(s)) return Number.POSITIVE_INFINITY;
  const yearMatch = s.match(/(19|20)\d{2}/);
  if (!yearMatch) return Number.NEGATIVE_INFINITY;
  const year = Number(yearMatch[0]);
  let month = 0;
  const nameIdx = MONTH_NAMES.findIndex((name) => s.includes(name));
  if (nameIdx >= 0) {
    month = nameIdx + 1;
  } else {
    const iso = s.match(/(?:19|20)\d{2}[-/.](\d{1,2})/);
    if (iso) month = Number(iso[1]);
  }
  return year * 12 + Math.min(Math.max(month, 0), 12);
}

/** Flag every entry tied for the most-recent (max) rank; no-op if none are dated. */
function markRecent(items: { target: PlacementTarget; rank: number }[]): void {
  let max = Number.NEGATIVE_INFINITY;
  for (const item of items) if (item.rank > max) max = item.rank;
  if (max === Number.NEGATIVE_INFINITY) return;
  for (const item of items) if (item.rank === max) item.target.recent = true;
}

/**
 * Placement chips for `add_keyword`: every skills category, plus enabled
 * experience entries, projects, and custom sections. Indices are into the FULL
 * resume arrays (disabled entries are skipped but survivors keep their original
 * array index — they are NOT renumbered to an enabled-only sequence; this matches
 * the tailor prompt). Entry-style custom sections use the same full-array rule;
 * bullet-style sections use their stable section key as a section-level sentinel.
 * Experience/project chips carry a display date and a `recent` flag. Custom dates
 * are deliberately not treated as recency evidence.
 */
export function buildPlacementTargets(resume: ResumeData): PlacementTarget[] {
  const targets: PlacementTarget[] = [];
  for (const group of resume.skills) {
    targets.push({
      section: "skills",
      index_or_category: group.category,
      label: group.category,
    });
  }

  const experienceTargets: { target: PlacementTarget; rank: number }[] = [];
  resume.experience.forEach((entry, index) => {
    if (entry.enabled === false) return;
    const endRaw = entry.end_date?.trim();
    // An empty end date means the role is current → most recent.
    const rank = endRaw ? dateSortKey(endRaw) : Number.POSITIVE_INFINITY;
    experienceTargets.push({
      target: {
        section: "experience",
        index_or_category: index,
        label: `${entry.company} — ${entry.role}`,
        date: endRaw || "Present",
      },
      rank,
    });
  });
  markRecent(experienceTargets);
  for (const item of experienceTargets) targets.push(item.target);

  const projectTargets: { target: PlacementTarget; rank: number }[] = [];
  resume.projects.forEach((project, index) => {
    if (project.enabled === false) return;
    const dateRaw = project.date?.trim();
    projectTargets.push({
      target: {
        section: "projects",
        index_or_category: index,
        label: project.name,
        date: dateRaw || null,
      },
      rank: dateSortKey(dateRaw),
    });
  });
  markRecent(projectTargets);
  for (const item of projectTargets) targets.push(item.target);

  for (const section of resume.extra_sections ?? []) {
    if (section.enabled === false) continue;
    if (section.type === "entries") {
      section.entries.forEach((entry, index) => {
        if (entry.enabled === false) return;
        targets.push({
          section: "extra",
          section_key: section.key,
          index_or_category: index,
          label: `${section.title} — ${entry.heading}`,
          date: entry.date?.trim() || null,
        });
      });
    } else if (section.type === "bullets") {
      // Mirror the backend exactly (placement_targets.build_targets / .canonicalize
      // only emit/accept type === "bullets"): a flat-bullets section uses its
      // stable section key as the section-level sentinel. Any other/unknown type
      // is excluded so the two target spaces cannot diverge.
      targets.push({
        section: "extra",
        section_key: section.key,
        index_or_category: section.key,
        label: section.title,
      });
    }
  }

  return targets;
}

export function enabledProjectNames(resume: ResumeData): string[] {
  return resume.projects
    .filter((project) => project.enabled !== false)
    .map((project) => project.name);
}

export function targetsEqual(a: SavedTarget, b: SavedTarget): boolean {
  return (
    a.section === b.section &&
    (a.section_key ?? null) === (b.section_key ?? null) &&
    String(a.index_or_category) === String(b.index_or_category)
  );
}

function targetKey(target: SavedTarget): string {
  return `${target.section}:${target.section_key ?? ""}:${target.index_or_category}`;
}

/** Segmented action control — renders ONLY the actions the gap allows. */
export function ActionSegment({
  actions,
  value,
  onSelect,
}: {
  actions: GapAction[];
  value: GapAction | null;
  onSelect: (action: GapAction) => void;
}) {
  const manual = actions.filter((action) => SEGMENT_ACTIONS.includes(action));
  if (manual.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Resolution action"
      className="bg-muted inline-flex w-fit items-center gap-0.5 rounded-lg p-[3px]"
    >
      {manual.map((action) => (
        <button
          key={action}
          type="button"
          aria-pressed={value === action}
          onClick={() => onSelect(action)}
          className={cn(
            "h-6 rounded-md px-2 text-xs font-medium transition-colors",
            value === action
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {ACTION_LABELS[action]}
        </button>
      ))}
    </div>
  );
}

export function Chip({
  selected,
  highlighted,
  date,
  recent,
  onClick,
  children,
}: {
  selected?: boolean;
  /** Enrichment suggestion (e.g. project candidate) — visually nudged, not preselected. */
  highlighted?: boolean;
  /** Optional date shown after the label (experience/project chips). */
  date?: string | null;
  /** Most-recent entry in its section — shows a subtle "recent" tag. */
  recent?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "inline-flex h-6 max-w-full items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
        !selected && highlighted && "border-primary/40 text-foreground ring-1 ring-primary/30",
      )}
    >
      {highlighted && !selected && <Sparkles className="text-primary size-3 shrink-0" />}
      <span className="truncate">{children}</span>
      {date && (
        <span
          className={cn(
            "shrink-0 text-[10px] tabular-nums",
            selected ? "text-primary-foreground/70" : "text-muted-foreground/70",
          )}
        >
          {date}
        </span>
      )}
      {recent && (
        <span
          className={cn(
            "shrink-0 rounded px-1 text-[10px] font-medium",
            selected
              ? "bg-primary-foreground/20 text-primary-foreground"
              : "bg-muted text-muted-foreground",
          )}
        >
          recent
        </span>
      )}
    </button>
  );
}

const LOAD_ERROR_MESSAGE =
  "Couldn't load the base resume. Answer or skip instead.";

/** Fallback skills bucket for unverified adds (backend creates it if absent). */
const ADDITIONAL_SKILLS_CATEGORY = "Additional Skills";

const UNVERIFIED_WARNING =
  "Unverified. You have no evidence of this skill on your resume. Only add skills you genuinely have, because recruiters may ask.";

export function AddKeywordControls({
  targets,
  selected,
  wording,
  loadError = false,
  unverified = false,
  onPick,
  onWordingChange,
}: {
  targets: PlacementTarget[] | null;
  selected: SavedTarget | null;
  wording: string;
  /** Base resume failed to load: placement chips are unavailable. */
  loadError?: boolean;
  /**
   * Missing-skill gap: no evidence exists on the resume. Restricts placement to
   * skills categories (+ an "Additional Skills" fallback) and shows a warning.
   */
  unverified?: boolean;
  onPick: (target: PlacementTarget) => void;
  onWordingChange: (value: string) => void;
}) {
  const wordingId = useId();
  if (targets === null) {
    if (loadError) {
      return <p className="text-destructive text-xs">{LOAD_ERROR_MESSAGE}</p>;
    }
    return (
      <p className="text-muted-foreground text-xs">Loading placement options…</p>
    );
  }
  let skillsItems = targets.filter((t) => t.section === "skills");
  if (unverified) {
    const hasAdditional = skillsItems.some(
      (t) =>
        String(t.index_or_category).toLowerCase() ===
        ADDITIONAL_SKILLS_CATEGORY.toLowerCase(),
    );
    if (!hasAdditional) {
      const fallback: PlacementTarget = {
        section: "skills",
        index_or_category: ADDITIONAL_SKILLS_CATEGORY,
        label: ADDITIONAL_SKILLS_CATEGORY,
      };
      skillsItems = [...skillsItems, fallback];
    }
  }
  const groups = (
    unverified
      ? [{ key: "skills", title: "Skills", items: skillsItems }]
      : [
          { key: "skills", title: "Skills", items: skillsItems },
          { key: "experience", title: "Experience", items: targets.filter((t) => t.section === "experience") },
          { key: "projects", title: "Projects", items: targets.filter((t) => t.section === "projects") },
          { key: "extra", title: "Custom", items: targets.filter((t) => t.section === "extra") },
        ]
  ).filter((group) => group.items.length > 0);

  return (
    <div className="space-y-2">
      {unverified && (
        <div className="text-destructive bg-destructive/10 rounded-md p-2 text-xs">
          {UNVERIFIED_WARNING}
        </div>
      )}
      <p className="text-muted-foreground text-xs">Where should this keyword live?</p>
      {groups.map((group) => (
        <div key={group.key} className="flex flex-wrap items-baseline gap-1.5">
          <span className="text-muted-foreground w-20 shrink-0 text-xs">
            {group.title}
          </span>
          {group.items.map((target) => (
            <Chip
              key={targetKey(target)}
              selected={selected !== null && targetsEqual(target, selected)}
              date={target.date}
              recent={target.recent}
              onClick={() => onPick(target)}
            >
              {target.label}
            </Chip>
          ))}
        </div>
      ))}
      <div className="grid gap-1.5">
        <Label htmlFor={wordingId} className="text-muted-foreground text-xs">
          Wording
        </Label>
        <Input
          id={wordingId}
          value={wording}
          onChange={(event) => onWordingChange(event.target.value)}
          placeholder="Exact wording to add"
        />
      </div>
    </div>
  );
}

export function UserInputControls({
  question,
  text,
  targets,
  selected,
  placeholder = "e.g. Built the ingestion pipeline in Python and Airflow",
  onTextChange,
  onPickTarget,
}: {
  question: string;
  text: string;
  /** Optional entry/custom-section chips a bullet could land on; null while loading. */
  targets: PlacementTarget[] | null;
  /** Currently attached role/project, or null (none is allowed). */
  selected: SavedTarget | null;
  /** Override the textarea placeholder (e.g. the summary value-prop draft). */
  placeholder?: string;
  onTextChange: (value: string) => void;
  /** Pass a target to attach it, or null to detach the current selection. */
  onPickTarget: (target: PlacementTarget | null) => void;
}) {
  const questionId = useId();
  return (
    <div className="space-y-2">
      <p id={questionId} className="text-sm">
        {question}
      </p>
      {/* The constraint has to stay on screen. It used to live in the
          placeholder, so it disappeared the moment you started writing. */}
      <p id={`${questionId}-hint`} className="text-muted-foreground text-xs">
        Only what you write here is used.
      </p>
      <Textarea
        aria-labelledby={questionId}
        aria-describedby={`${questionId}-hint`}
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        placeholder={placeholder}
      />
      {targets && targets.length > 0 && (
        <div className="space-y-1">
          <p className="text-muted-foreground text-xs">
            Which role, project, or custom section was this?{" "}
            <span className="opacity-70">(optional)</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {targets.map((target) => {
              const isSelected =
                selected !== null && targetsEqual(target, selected);
              return (
                <Chip
                  key={targetKey(target)}
                  selected={isSelected}
                  date={target.date}
                  recent={target.recent}
                  onClick={() => onPickTarget(isSelected ? null : target)}
                >
                  {target.label}
                </Chip>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// --- "Found in your library" -------------------------------------------------

const KB_SNIPPET_MAX = 60;

function clip(text: string, max: number): string {
  const s = text.trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/**
 * Stable identity for a candidate chip. `disabled` candidates are identified by
 * the entry they point at, KB ones by their point/entity id, and the profile
 * candidate is a singleton per gap — the same keys the selection check compares
 * a stored resolution against.
 */
export function candidateKey(candidate: LibraryCandidate): string {
  if (candidate.kind === "disabled") {
    return `disabled:${candidate.section}:${candidate.index}`;
  }
  if (candidate.kind === "profile") return "profile";
  return `${candidate.kind}:${candidate.entity_id ?? ""}:${candidate.point_id ?? ""}`;
}

/** Chip text per design §4.2: disabled entries name themselves, KB items lead with "KB:". */
export function candidateLabel(candidate: LibraryCandidate): string {
  if (candidate.kind === "disabled") {
    const name = (candidate.name ?? "").trim() || "Hidden entry";
    return `${clip(name, 40)} (disabled)`;
  }
  if (candidate.kind === "profile") return "KB profile";
  const text =
    (candidate.evidence_snippet ?? "").trim() ||
    (candidate.title ?? "").trim() ||
    "Career KB item";
  return `KB: ${clip(text, KB_SNIPPET_MAX)}`;
}

/**
 * Evidence the resolver found in the user's own material — the third chip class,
 * distinct from placement chips (where a keyword goes) and project chips (what to
 * attach). `auto` chips are already applied, so they render selected; the rest are
 * suggestions that route to the Answer box (the server rejects them as
 * `enable_entry`/`port_kb_point`, by design — they never passed the evidence gate).
 */
export function LibraryCandidateChips({
  candidates,
  selectedKey,
  onPick,
}: {
  candidates: LibraryCandidate[];
  /** `candidateKey` of the candidate the current resolution came from, if any. */
  selectedKey: string | null;
  onPick: (candidate: LibraryCandidate) => void;
}) {
  if (candidates.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Library className="size-3.5 shrink-0" />
        Found in your library
      </p>
      <div className="flex flex-wrap gap-1.5">
        {candidates.map((candidate) => {
          const key = candidateKey(candidate);
          return (
            <Chip
              key={key}
              selected={selectedKey === key}
              highlighted={candidate.auto && selectedKey !== key}
              onClick={() => onPick(candidate)}
            >
              {candidateLabel(candidate)}
            </Chip>
          );
        })}
      </div>
      <p className="text-muted-foreground/80 text-xs">
        Evidence from your own resume entries and Career KB. Picking one that
        can&apos;t be ported directly drops its text into the answer box for you
        to edit.
      </p>
    </div>
  );
}

export function AttachProjectControls({
  projects,
  candidates,
  selected,
  loadError = false,
  onPick,
}: {
  projects: string[] | null;
  /** enrichment.project_candidates — highlighted as suggestions. */
  candidates: string[];
  selected: string | null;
  /** Base resume failed to load: project chips are unavailable. */
  loadError?: boolean;
  onPick: (name: string) => void;
}) {
  if (projects === null) {
    if (loadError) {
      return <p className="text-destructive text-xs">{LOAD_ERROR_MESSAGE}</p>;
    }
    return <p className="text-muted-foreground text-xs">Loading projects…</p>;
  }
  if (projects.length === 0) {
    return (
      <p className="text-muted-foreground text-xs">
        No projects on this base resume. Try answering instead.
      </p>
    );
  }
  const candidateSet = new Set(candidates.map((name) => name.toLowerCase()));
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs">
        Attach an existing project as evidence for this skill.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {projects.map((name) => (
          <Chip
            key={name}
            selected={selected === name}
            highlighted={candidateSet.has(name.toLowerCase())}
            onClick={() => onPick(name)}
          >
            {name}
          </Chip>
        ))}
      </div>
    </div>
  );
}
