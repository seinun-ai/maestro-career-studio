"use client";

import { useRef, useState } from "react";
import { Check, Library, Undo2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ActionSegment,
  AddKeywordControls,
  AttachProjectControls,
  LibraryCandidateChips,
  UserInputControls,
  candidateKey,
  targetsEqual,
  type PlacementTarget,
  type SavedTarget,
} from "@/components/gap-analysis/resolution-controls";
import {
  isAutoResolved,
  resolutionProvenance,
  type Gap,
  type GapAction,
  type LibraryCandidate,
  type Resolution,
} from "@/lib/types";

function payloadTarget(payload: Record<string, unknown>): SavedTarget | null {
  const raw = payload.placement_target;
  if (typeof raw !== "object" || raw === null) return null;
  const target = raw as { section?: unknown; index_or_category?: unknown };
  if (typeof target.section !== "string") return null;
  if (
    typeof target.index_or_category !== "string" &&
    typeof target.index_or_category !== "number"
  ) {
    return null;
  }
  const sectionKey = (raw as { section_key?: unknown }).section_key;
  if (target.section === "extra") {
    if (typeof sectionKey !== "string") return null;
    return {
      section: "extra",
      section_key: sectionKey,
      index_or_category: target.index_or_category,
    };
  }
  if (
    target.section !== "skills" &&
    target.section !== "experience" &&
    target.section !== "projects"
  ) {
    return null;
  }
  return { section: target.section, index_or_category: target.index_or_category };
}

function payloadString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

/**
 * F2 — the wording prefill splits on the placement section: a Skills placement wants
 * the exact JD token; a bullet (experience/projects, or no target yet) wants the
 * natural suggested phrasing, falling back to the token.
 */
function suggestedWordingForSection(
  gap: Gap,
  section: string | undefined,
): string {
  if (section === "skills") {
    return gap.jd_skill || gap.enrichment?.suggested_wording || "";
  }
  return gap.enrichment?.suggested_wording || gap.jd_skill || "";
}

/**
 * F1 — resolve the enrichment's suggested placement to a chip that ACTUALLY exists.
 * Returns null (→ no pre-selection) unless the suggestion matches a real chip from
 * `buildPlacementTargets`. Two guards make this safe:
 *  - Missing-skill gaps are unverified, so only a Skills placement may pre-select
 *    (mirrors the skills-only restriction in AddKeywordControls, so custom
 *    sections cannot become a loophole for an unverified add).
 *  - Backend and frontend both retain FULL-array indices for entry targets. Custom
 *    targets additionally match the exact section_key (and the section-key sentinel
 *    for bullet-style sections). Requiring an exact live-chip match means any stale,
 *    disabled, or absent target yields no pre-selection rather than a wrong chip.
 */
function resolveSuggestedTarget(
  targets: PlacementTarget[],
  gap: Gap,
  isMissingSkill: boolean,
): SavedTarget | null {
  const suggestion = gap.enrichment?.suggested_placement;
  if (!suggestion) return null;
  if (isMissingSkill && suggestion.section !== "skills") return null;
  const match = targets.find((t) => targetsEqual(t, suggestion));
  if (!match) return null;
  return savedTarget(match);
}

function savedTarget(target: PlacementTarget): SavedTarget {
  if (target.section === "extra") {
    return {
      section: "extra",
      section_key: target.section_key,
      index_or_category: target.index_or_category,
    };
  }
  return {
    section: target.section,
    index_or_category: target.index_or_category,
  };
}

function userInputPayload(
  text: string,
  target: SavedTarget | null,
): Record<string, unknown> {
  return target ? { text, placement_target: target } : { text };
}

function gapTitle(gap: Gap): string {
  if (gap.kind === "skill") return gap.jd_skill ?? gap.gap_id;
  if (gap.kind === "title") return "Title alignment";
  if (gap.kind === "gate") return "Experience gate";
  if (gap.kind === "summary") return "Professional summary";
  if (gap.kind === "requirement") return gap.jd_skill ?? "Responsibility coverage";
  return "Format";
}

/**
 * F4 — a SKILL gap carries `potential_points`: a deterministic COARSE UPPER BOUND
 * (0-100 composite scale) of the headroom this fix could recover if it were the sole
 * driver of its subscore. Framed as a relative "up to +X" signal, never an exact
 * promise. Omitted when absent or rounding to zero (e.g. hygiene mirror_wording).
 */
function formatPotentialPoints(value: number | undefined): string | null {
  if (typeof value !== "number" || !(value > 0)) return null;
  return `up to +${value.toFixed(1)} pts`;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const REQUIREMENT_VARIANTS: Record<string, "destructive" | "secondary" | "outline"> = {
  required: "destructive",
  preferred: "secondary",
  mentioned: "outline",
};

function resolutionSummary(
  resolution: Resolution,
  targets: PlacementTarget[] | null,
): string {
  if (resolution.action === "add_keyword") {
    const saved = payloadTarget(resolution.payload);
    if (!saved) return `add “${payloadString(resolution.payload, "wording")}”`;
    // Skills categories (incl. the "Additional Skills" fallback bucket) may not
    // exist on the base resume yet, so fall back to the category name string.
    const label =
      targets?.find((t) => targetsEqual(t, saved))?.label ??
      (typeof saved.index_or_category === "string"
        ? saved.index_or_category
        : saved.section);
    return `add “${payloadString(resolution.payload, "wording")}” → ${label}`;
  }
  if (resolution.action === "user_input") {
    return `answered: “${truncate(payloadString(resolution.payload, "text"), 80)}”`;
  }
  if (resolution.action === "attach_project") {
    return `attach project “${payloadString(resolution.payload, "project_name")}”`;
  }
  if (resolution.action === "enable_entry") {
    const name = payloadString(resolution.payload, "name");
    const section = payloadString(resolution.payload, "section") || "entry";
    return name
      ? `unhide “${name}” from your ${section}`
      : `unhide a hidden ${section} entry`;
  }
  if (resolution.action === "port_kb_point") {
    const saved = payloadTarget(resolution.payload);
    const wording = truncate(payloadString(resolution.payload, "wording"), 60);
    const label = saved
      ? (targets?.find((t) => targetsEqual(t, saved))?.label ?? saved.section)
      : null;
    return label
      ? `add “${wording}” from your Career KB → ${label}`
      : `add “${wording}” from your Career KB`;
  }
  return "skipped";
}

/**
 * The one-line "where did this come from" caption on an auto-resolved card.
 * Reads `payload.provenance`, which only the resolver stamps — a hand-made
 * resolution has none and never renders as auto-resolved.
 */
function provenanceLine(resolution: Resolution): string | null {
  const provenance = resolutionProvenance(resolution);
  if (!provenance) return null;
  if (provenance.source === "library_auto") {
    const name = payloadString(resolution.payload, "name");
    return name
      ? `Auto-resolved from your library by enabling ${name}`
      : "Auto-resolved from your library";
  }
  if (provenance.source === "kb_profile") {
    return "Auto-resolved from your Career KB profile";
  }
  if (provenance.source === "wording_auto") {
    return "Auto-added the JD's exact term — this skill is already evidenced on your resume";
  }
  return "Auto-resolved from your Career KB";
}

/**
 * Which library chip the CURRENT resolution came from, so it renders selected.
 * Matches on the same identity `candidateKey` builds: entry coordinates for
 * disabled entries, the point id for KB ports, the singleton profile chip for a
 * kb_profile-provenance keyword add.
 */
function selectedCandidateKey(
  resolution: Resolution | undefined,
  candidates: LibraryCandidate[],
): string | null {
  if (!resolution) return null;
  if (resolution.action === "enable_entry") {
    const section = payloadString(resolution.payload, "section");
    const index = resolution.payload.index;
    return `disabled:${section}:${typeof index === "number" ? index : ""}`;
  }
  if (resolution.action === "port_kb_point") {
    const pointId = payloadString(resolution.payload, "kb_point_id");
    const match = candidates.find(
      (candidate) => (candidate.point_id ?? "") === pointId,
    );
    return match ? candidateKey(match) : null;
  }
  if (resolutionProvenance(resolution)?.source === "kb_profile") return "profile";
  return null;
}

/** Diagnostic evidence: match form, placement, recency, evidence entries. */
function EvidenceLine({ gap }: { gap: Gap }) {
  const diagnostic = gap.diagnostic;
  const bits: string[] = [];
  if (diagnostic.matched && diagnostic.match_form) {
    bits.push(
      diagnostic.matched_term
        ? `matched via ${diagnostic.match_form} (“${diagnostic.matched_term}”)`
        : `matched via ${diagnostic.match_form}`,
    );
  }
  if (diagnostic.placement) bits.push(diagnostic.placement.replace(/_/g, " "));
  if (diagnostic.last_used) bits.push(`last used ${diagnostic.last_used}`);
  if (diagnostic.tier) bits.push(`title tier: ${diagnostic.tier}`);
  const entries = diagnostic.evidence_entries ?? [];
  if (bits.length === 0 && entries.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {bits.length > 0 && (
        <span className="text-muted-foreground text-xs">{bits.join(" · ")}</span>
      )}
      {entries.map((entry) => (
        <Badge key={entry} variant="outline" className="font-normal">
          {entry}
        </Badge>
      ))}
    </div>
  );
}

/**
 * One gap: evidence + segmented action control + per-action inputs.
 * Commits a Resolution upward on every meaningful change (parent debounces
 * the save); commits `null` when the draft becomes invalid/unresolved.
 */
export function GapCard({
  gap,
  resolution,
  targets,
  projects,
  baseResumeError = false,
  onChange,
}: {
  gap: Gap;
  resolution: Resolution | undefined;
  /** Placement chips from the base resume; null while it loads. */
  targets: PlacementTarget[] | null;
  /** Enabled project names from the base resume; null while it loads. */
  projects: string[] | null;
  /** True when the base resume failed to load — chip actions show an error line. */
  baseResumeError?: boolean;
  onChange: (resolution: Resolution | null) => void;
}) {
  // Missing-skill gap: the skill is absent from the resume, so an add_keyword is
  // unverified — restrict placement to skills and warn the user.
  const isMissingSkill =
    gap.kind === "skill" && gap.diagnostic.fix_hint === "absent";

  const [editing, setEditing] = useState(resolution === undefined);
  const [action, setAction] = useState<GapAction | null>(resolution?.action ?? null);
  const [target, setTarget] = useState<SavedTarget | null>(() =>
    resolution?.action === "add_keyword" ? payloadTarget(resolution.payload) : null,
  );
  const [wording, setWording] = useState<string>(() => {
    const existing =
      resolution?.action === "add_keyword"
        ? payloadString(resolution.payload, "wording")
        : "";
    if (existing) return existing;
    // Default section before a chip is chosen: missing-skill gaps always land in
    // Skills (terse JD token); otherwise assume a bullet (natural phrasing). The
    // pre-select block below refines this once the suggested chip resolves.
    return suggestedWordingForSection(gap, isMissingSkill ? "skills" : undefined);
  });
  const [text, setText] = useState<string>(() => {
    if (resolution?.action === "user_input") {
      return payloadString(resolution.payload, "text");
    }
    // F6a — the summary gap prefills its value-proposition textarea from the
    // enrichment draft; committing it (via "Answer") refreshes the summary section.
    if (gap.kind === "summary") return gap.enrichment?.suggested_wording ?? "";
    return "";
  });
  const [inputTarget, setInputTarget] = useState<SavedTarget | null>(() =>
    resolution?.action === "user_input" ? payloadTarget(resolution.payload) : null,
  );
  const [project, setProject] = useState<string | null>(() =>
    resolution?.action === "attach_project"
      ? payloadString(resolution.payload, "project_name") || null
      : null,
  );

  // Once the user hand-edits the wording we stop re-deriving it from the section.
  // An existing add_keyword resolution already owns its wording, so treat it as
  // touched so a later chip pick never clobbers a saved value. Read only in event
  // handlers (never during render).
  const wordingTouchedRef = useRef(resolution?.action === "add_keyword");
  // The suggested-placement pre-select runs at most once, when `targets` load.
  const [presetApplied, setPresetApplied] = useState(false);

  const commit = (nextAction: GapAction, payload: Record<string, unknown>) =>
    onChange({ gap_id: gap.gap_id, action: nextAction, payload });
  const clear = () => onChange(null);

  // F1 — pre-select the chip matching enrichment.suggested_placement, validated
  // against the real chips. `targets` load asynchronously (null until the base
  // resume arrives), so we apply the suggestion during render the first time they
  // resolve — the sanctioned alternative to a state-syncing effect. It never commits
  // a resolution (the gap stays open until the user engages) and never overrides an
  // existing resolution. The wording input is hidden while `targets` is null, so the
  // wording is still pristine when this fires and can be re-derived for the section.
  if (!presetApplied && targets !== null) {
    setPresetApplied(true);
    if (!resolution) {
      const suggested = resolveSuggestedTarget(targets, gap, isMissingSkill);
      if (suggested) {
        setTarget(suggested);
        setWording(suggestedWordingForSection(gap, suggested.section));
      }
    }
  }

  const selectAction = (next: GapAction) => {
    setAction(next);
    if (next === "skip") {
      setEditing(false);
      commit("skip", {});
      return;
    }
    // Switching back to an action whose draft is still valid re-commits it;
    // otherwise the gap goes back to unresolved until the draft is complete.
    if (next === "add_keyword" && target && wording.trim()) {
      commit("add_keyword", { placement_target: target, wording: wording.trim() });
    } else if (next === "user_input" && text.trim()) {
      commit("user_input", userInputPayload(text.trim(), inputTarget));
    } else if (next === "attach_project" && project) {
      commit("attach_project", { project_name: project });
    } else if (resolution && !isAutoResolved(resolution)) {
      // An auto-resolution survives merely LOOKING at another action — it is
      // the system's proposal, and only Skip/Undo or a completed alternative
      // may retract it. (Selecting a tab used to wipe it silently.)
      clear();
    }
  };

  const libraryCandidates = gap.library_candidates ?? [];

  /**
   * A library chip is the only way to produce `enable_entry` / `port_kb_point`:
   * their payloads are the verified candidate's own coordinates, and the server
   * re-runs the same evidence gate on save. A candidate that did NOT pass the
   * gate (`auto: false`, a draft point, or no canonical target) would be
   * rejected, so it routes to the Answer box with its text prefilled instead —
   * the honest path, and what design §4.2 asks for when `placement_target` is
   * null.
   */
  const applyCandidate = (candidate: LibraryCandidate) => {
    if (
      candidate.kind === "disabled" &&
      candidate.auto &&
      (candidate.section === "experience" || candidate.section === "projects") &&
      typeof candidate.index === "number"
    ) {
      setAction("enable_entry");
      setEditing(false);
      commit("enable_entry", {
        section: candidate.section,
        index: candidate.index,
        name: candidate.name ?? "",
        provenance: { source: "library_auto" },
      });
      return;
    }
    if (
      candidate.kind === "kb_point" &&
      candidate.auto &&
      candidate.point_id &&
      candidate.placement_target
    ) {
      setAction("port_kb_point");
      setEditing(false);
      commit("port_kb_point", {
        kb_point_id: candidate.point_id,
        ...(candidate.entity_id ? { kb_entity_id: candidate.entity_id } : {}),
        placement_target: candidate.placement_target,
        wording: candidate.evidence_snippet ?? "",
        provenance: {
          source: "kb_auto",
          kb_point_id: candidate.point_id,
          ...(candidate.entity_id ? { kb_entity_id: candidate.entity_id } : {}),
        },
      });
      return;
    }
    // Profile evidence is a bare skills claim — no prose to port, so hand the
    // user the keyword flow (placement stays skills-only for a missing skill).
    if (candidate.kind === "profile" || !gap.actions.includes("user_input")) {
      setAction("add_keyword");
      return;
    }
    const snippet = (
      candidate.evidence_snippet ??
      candidate.title ??
      candidate.name ??
      ""
    ).trim();
    setAction("user_input");
    if (!snippet) return;
    const nextTarget =
      candidate.placement_target && candidate.placement_target.section !== "skills"
        ? (candidate.placement_target as SavedTarget)
        : inputTarget;
    setText(snippet);
    setInputTarget(nextTarget);
    commit("user_input", userInputPayload(snippet, nextTarget));
  };

  const title = gapTitle(gap);
  const isSummary = gap.kind === "summary";
  const potentialPointsLabel =
    gap.kind === "skill" ? formatPotentialPoints(gap.potential_points) : null;
  // Optional placement chips for user_input: a bullet lands on an experience,
  // project, or custom-section target, so drop the skills chips here. A summary is
  // its own section, so it never attaches to an entry.
  const inputTargets = isSummary
    ? null
    : targets?.filter((t) => t.section !== "skills") ?? null;

  if (!editing && resolution?.action === "skip") {
    return (
      <div className="text-muted-foreground flex items-center justify-between gap-2 rounded-xl border border-dashed py-1.5 pr-1.5 pl-4 text-sm">
        <span className="truncate">{title} — skipped</span>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => {
            clear();
            setAction(null);
            setEditing(true);
          }}
        >
          <Undo2 /> Undo
        </Button>
      </div>
    );
  }

  // Auto-resolved: the resolver already stored this resolution at session
  // creation, so the card opens RESOLVED with its provenance shown and a
  // one-click Undo (which saves `skip` through the normal autosave) rather than
  // as an untouched gap — and rather than the "skipped" label the generic
  // summary used to fall through to.
  if (!editing && resolution && isAutoResolved(resolution)) {
    return (
      <div className="border-primary/25 bg-primary/[0.04] flex flex-wrap items-center gap-2 rounded-xl border px-4 py-2.5 text-sm">
        <Library className="text-primary size-4 shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="font-medium">{title}</span>
          <span className="text-muted-foreground">
            {" "}
            · {resolutionSummary(resolution, targets)}
          </span>
          <span className="text-muted-foreground block text-xs">
            {provenanceLine(resolution)}
          </span>
        </span>
        <Button variant="ghost" size="xs" onClick={() => setEditing(true)}>
          Change
        </Button>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => {
            setAction("skip");
            commit("skip", {});
          }}
        >
          <Undo2 /> Undo
        </Button>
      </div>
    );
  }

  if (!editing && resolution) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="bg-card ring-foreground/10 hover:ring-primary/40 flex w-full items-center gap-2 rounded-xl px-4 py-2.5 text-left text-sm ring-1 transition-shadow"
      >
        <Check className="text-primary size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">
          <span className="font-medium">{title}</span>
          <span className="text-muted-foreground">
            {" "}
            · {resolutionSummary(resolution, targets)}
          </span>
        </span>
        <span className="text-muted-foreground shrink-0 text-xs">Edit</span>
      </button>
    );
  }

  return (
    <Card size="sm">
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {resolution && resolution.action !== "skip" && (
            <Check className="text-primary size-4 shrink-0" />
          )}
          <span className="text-sm font-medium">{title}</span>
          {gap.kind === "skill" && gap.requirement_level && (
            <Badge variant={REQUIREMENT_VARIANTS[gap.requirement_level] ?? "outline"}>
              {gap.requirement_level}
            </Badge>
          )}
          {potentialPointsLabel && (
            <Badge
              variant="outline"
              className="font-normal"
              title="Coarse upper bound if this were the only fix. A relative signal, not an exact promise."
            >
              {potentialPointsLabel}
            </Badge>
          )}
          {resolution && (
            <Button
              variant="ghost"
              size="xs"
              className="ml-auto"
              onClick={() => setEditing(false)}
            >
              Done
            </Button>
          )}
        </div>
        {gap.detail && <p className="text-muted-foreground text-xs">{gap.detail}</p>}
        <EvidenceLine gap={gap} />
        {/* F6c — mirror_wording gaps split their note on score_effect: hygiene never
            moves the score; adds_credit gains real keyword credit. */}
        {gap.score_effect && (
          <p className="text-muted-foreground text-xs">
            {gap.score_effect === "hygiene"
              ? "Exact-token hygiene: helps recruiter keyword search, but will not change the score."
              : "Semantic match: adding the literal JD token adds keyword credit."}
          </p>
        )}
        <ActionSegment actions={gap.actions} value={action} onSelect={selectAction} />
        <LibraryCandidateChips
          candidates={libraryCandidates}
          selectedKey={selectedCandidateKey(resolution, libraryCandidates)}
          onPick={applyCandidate}
        />
        {action === "add_keyword" && (
          <AddKeywordControls
            targets={targets}
            loadError={baseResumeError}
            unverified={isMissingSkill}
            selected={target}
            wording={wording}
            onPick={(picked) => {
              const saved = savedTarget(picked);
              setTarget(saved);
              // F2: unless the user hand-edited the wording, re-derive it for the
              // picked section (skills → terse JD token; bullet → suggested phrasing).
              const nextWording = wordingTouchedRef.current
                ? wording
                : suggestedWordingForSection(gap, saved.section);
              if (nextWording !== wording) setWording(nextWording);
              if (nextWording.trim()) {
                commit("add_keyword", {
                  placement_target: saved,
                  wording: nextWording.trim(),
                });
              } else if (resolution) {
                clear();
              }
            }}
            onWordingChange={(value) => {
              wordingTouchedRef.current = true;
              setWording(value);
              if (!target) return;
              if (value.trim()) {
                commit("add_keyword", {
                  placement_target: target,
                  wording: value.trim(),
                });
              } else if (resolution) {
                clear();
              }
            }}
          />
        )}
        {action === "user_input" && (
          <UserInputControls
            question={
              isSummary
                ? "Rewrite your summary as a JD-aligned value proposition. This refreshes the summary section."
                : gap.enrichment?.elicitation_question ??
                  (gap.kind === "requirement"
                    ? "How does your experience cover this responsibility?"
                    : "What's your actual experience with this?")
            }
            placeholder={
              isSummary
                ? "Draft your JD-aligned value proposition. This becomes your summary."
                : undefined
            }
            text={text}
            targets={inputTargets}
            selected={inputTarget}
            onTextChange={(value) => {
              setText(value);
              if (value.trim()) {
                commit("user_input", userInputPayload(value.trim(), inputTarget));
              } else if (resolution) {
                clear();
              }
            }}
            onPickTarget={(picked) => {
              const saved: SavedTarget | null = picked
                ? savedTarget(picked)
                : null;
              setInputTarget(saved);
              // Placement is optional metadata on top of the answer — only commit
              // when there's actual answer text (text is the required field).
              if (text.trim()) {
                commit("user_input", userInputPayload(text.trim(), saved));
              }
            }}
          />
        )}
        {action === "attach_project" && (
          <AttachProjectControls
            projects={projects}
            loadError={baseResumeError}
            candidates={gap.enrichment?.project_candidates ?? []}
            selected={project}
            onPick={(name) => {
              setProject(name);
              commit("attach_project", { project_name: name });
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}
