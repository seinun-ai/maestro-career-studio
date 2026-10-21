"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Loader2 } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { CONFIRM_MS, FADE_MS } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { SegmentTone } from "@/components/visual";
import { APPLICATION_STATUSES, type ApplicationStatus } from "@/lib/types";

/** One colour role per status: its container pair for the chip, the role
 * itself for the dot. The roles carry both themes (app/globals.css). */
const STATUS_STYLES: Record<
  ApplicationStatus,
  { label: string; chip: string; dot: string }
> = {
  draft: {
    label: "Draft",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/60",
  },
  applied: {
    label: "Applied",
    chip: "bg-primary-container text-on-primary-container",
    dot: "bg-primary",
  },
  interviewing: {
    label: "Interviewing",
    chip: "bg-warning-container text-on-warning-container",
    dot: "bg-warning",
  },
  offered: {
    label: "Offer",
    chip: "bg-tertiary-container text-on-tertiary-container",
    dot: "bg-tertiary",
  },
  accepted: {
    label: "Offer accepted",
    chip: "bg-success-container text-on-success-container",
    dot: "bg-success",
  },
  rejected: {
    label: "Rejected",
    chip: "bg-error-container text-on-error-container",
    dot: "bg-destructive",
  },
  withdrawn: {
    label: "Withdrawn",
    chip: "bg-muted text-muted-foreground line-through decoration-muted-foreground/40",
    dot: "bg-muted-foreground/40",
  },
};

/** The bar-segment tone for each status: the same roles as the dots above (the dots dim draft and
 * withdrawn with /60 and /40; a bar segment has no room for that). Analytics' status mix reads this. */
export const STATUS_TONES: Record<ApplicationStatus, SegmentTone> = {
  draft: "muted",
  applied: "primary",
  interviewing: "warning",
  offered: "tertiary",
  accepted: "success",
  rejected: "error",
  withdrawn: "muted",
};

export function statusLabel(status: string | null): string {
  if (!status) return "Draft";
  return STATUS_STYLES[status as ApplicationStatus]?.label ?? "Unknown";
}

/** `locked` is a chip that can be focused but not changed: no pointer cursor, no hover lift, still a focus ring. */
function chipClasses(interactive: boolean, locked = false): string {
  return cn(
    "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-label-medium",
    interactive &&
      "cursor-pointer transition-[background-color,color,scale,box-shadow] duration-(--duration-short3) ease-(--ease-standard) select-none " +
        "hover:shadow-level1 active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring",
    locked && "cursor-default select-none focus-visible:outline-2 focus-visible:outline-ring",
  );
}

/** A status's own dot, for places that list statuses without the chip (filters, analytics). */
export function StatusDot({ status, className }: { status: ApplicationStatus; className?: string }) {
  return <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", STATUS_STYLES[status].dot, className)} />;
}

/** Static pill for jobs that have no application yet ("Saved"). */
export function SavedChip() {
  return (
    <span
      className={cn(
        chipClasses(false),
        "border border-dashed text-muted-foreground",
      )}
    >
      <span className="size-1.5 rounded-full bg-muted-foreground/40" />
      Saved
    </span>
  );
}

// needs_decision and needs_human are ONE state to the user ("Needs you"), so they
// share one object: one label, one colour. The attention role (orange), not
// warning (amber): warning is the application chip's "Interviewing", which
// sits in the same tracker column. Contrast pinned in
// test_frontend_design_tokens.py.
const NEEDS_YOU = {
  label: "Needs you",
  className: "bg-attention-container text-on-attention-container",
  dot: "bg-attention",
};

/** Derived agent-lane state for a saved (no-application) job, from its newest
 * proposal — Skipped/Expired are clear terminal answers instead of a flat
 * "Saved" hiding what happened; open states show where the pipeline stands.
 * "Skipped" (not "Declined") for a rejected proposal: you passed on the
 * agent's suggestion, which is the opposite of an application's "Rejected". */
/**
 * The ONE proposal-status vocabulary, covering the full enum.
 *
 * There were two. This file carried the tracker's six-state map while
 * `proposals-section.tsx` carried its own nine-state `STATUS_LABELS`, and they
 * disagreed on four of the six they shared: `accepted` read "Queued" here and
 * "Accepted" there, `pending_review` read "Proposed" vs "Pending review", and
 * `needs_decision`/`needs_human` collapsed to "Needs you" here but split into
 * two labels there. Same enum, same user, two dictionaries — exactly what §8's
 * "StatusChip is the ONLY status vocabulary" rule exists to prevent.
 *
 * The tracker's wording wins because it is the DOCUMENTED one: SYSTEM.md §5
 * step 2 defines the agent lane as proposed / queued / needs_you / skipped, and
 * `AGENT_LANE_LABELS` in the Jobs page filter already says exactly that.
 * Of the states the tracker never renders, approved keeps its literal name;
 * submitted reads Applied and submission_uncertain Check if sent (the owner's
 * chip words, appendix D §0).
 *
 * Consequence worth stating: the Proposals page no longer distinguishes
 * `needs_decision` from `needs_human` in the badge. That is deliberate — it
 * already groups both into one NEEDS_YOU lane, so the lane heading carries the
 * distinction and the badge was repeating a split the layout had already made.
 */
export const PROPOSAL_STATUS_CHIP: Record<
  string,
  { label: string; className: string; dot: string }
> = {
  pending_review: { label: "Proposed", className: "bg-primary-container text-on-primary-container", dot: "bg-primary" },
  needs_decision: NEEDS_YOU,
  needs_human: NEEDS_YOU,
  accepted: { label: "Queued", className: "bg-secondary-container text-on-secondary-container", dot: "bg-on-secondary-container" },
  approved: { label: "Approved", className: "bg-success-container text-on-success-container", dot: "bg-success" },
  submitted: { label: "Applied", className: "bg-success-container text-on-success-container", dot: "bg-success" },
  submission_uncertain: { label: "Check if sent", className: "bg-attention-container text-on-attention-container", dot: "bg-attention" },
  rejected: { label: "Skipped", className: "text-muted-foreground bg-muted", dot: "bg-muted-foreground/60" },
  expired: { label: "Expired", className: "text-muted-foreground bg-muted", dot: "bg-muted-foreground/60" },
};

/** A proposal status's own dot, for the inbox lanes' headings and filters (the chip is hidden there, D5). */
export function LaneDot({ status, className }: { status: string; className?: string }) {
  const dot = PROPOSAL_STATUS_CHIP[status]?.dot;
  if (!dot) return null;
  return <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", dot, className)} />;
}

const AGENT_LANE_CHIP = PROPOSAL_STATUS_CHIP;

export function SavedJobChip({
  proposalStatus,
}: {
  proposalStatus?: string | null;
}) {
  const derived = proposalStatus ? AGENT_LANE_CHIP[proposalStatus] : undefined;
  if (!derived) return <SavedChip />;
  return (
    <span className={cn(chipClasses(false), derived.className)}>
      <span className="size-1.5 rounded-full bg-current opacity-40" />
      {derived.label}
    </span>
  );
}

/**
 * Inline application status: a tonal pill that opens the status menu right
 * where it is rendered (table row, job header) — one click to change, no
 * drill-down. PATCHing is the caller's job via onSelect.
 */
export function StatusChip({
  status,
  onSelect,
  pending = false,
  disabled = false,
  lockedReason,
  className,
}: {
  status: string | null;
  onSelect: (status: ApplicationStatus) => void;
  pending?: boolean;
  disabled?: boolean;
  /** Why the chip cannot change right now (a job moving between copies): the chevron becomes a lock and the
   * chip refuses to open but stays focusable, like a pending one. */
  lockedReason?: string;
  className?: string;
}) {
  const current = (status ?? "draft") as ApplicationStatus;
  const style = STATUS_STYLES[current] ?? STATUS_STYLES.draft;

  // A new status cross-fades in over the old one (a 2px blur between, `animate-status-in`/`-out`, FADE_MS), not on
  // first paint. The old label stays, stacked under the new one, until the fade ends.
  const [shownStatus, setShownStatus] = useState(current);
  const [leaving, setLeaving] = useState<ApplicationStatus | null>(null);
  const fadeEnds = useRef(0);
  if (shownStatus !== current) {
    setLeaving(shownStatus);
    setShownStatus(current);
  }
  useEffect(() => {
    if (leaving == null) return;
    fadeEnds.current = performance.now() + FADE_MS;
    const t = window.setTimeout(() => setLeaving(null), FADE_MS);
    return () => window.clearTimeout(t);
  }, [leaving]);
  // Then one soft ring pulse once the change has settled, never before the fade ends: not on first paint, and
  // not when a failed PATCH rolls the status back to what it was before.
  const settled = useRef(current);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (pending || settled.current === current) return;
    settled.current = current;
    let off = 0;
    const on = window.setTimeout(() => {
      setConfirm(true);
      off = window.setTimeout(() => setConfirm(false), CONFIRM_MS);
    }, Math.max(0, fadeEnds.current - performance.now()));
    return () => {
      window.clearTimeout(on);
      window.clearTimeout(off);
    };
  }, [current, pending]);
  // A natively disabled trigger cannot take focus back when the menu closes, so
  // the chip stays focusable (aria-disabled) and just refuses to open meanwhile.
  const [open, setOpen] = useState(false);
  const reasonId = useId();
  const locked = disabled || !!lockedReason;
  const blocked = pending || !!lockedReason;

  return (
    <DropdownMenu
      open={open && !blocked}
      onOpenChange={(next) => {
        if (!blocked) setOpen(next);
      }}
    >
      <DropdownMenuTrigger
        render={
          // data-status-chip: what a list hands focus to when a status change
          // removes this chip's row (the next row's chip).
          <button
            type="button"
            data-status-chip
            disabled={disabled}
            aria-disabled={blocked || undefined}
            aria-describedby={lockedReason ? reasonId : undefined}
            data-confirm={confirm || undefined}
            title={lockedReason}
            aria-label={locked ? `Status: ${style.label}` : `Status: ${style.label}. Change status`}
            className={cn(chipClasses(!locked, locked), style.chip, "data-confirm:animate-confirm", className)}
            onClick={(e) => e.stopPropagation()}
          >
            {pending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <span className={cn("size-1.5 rounded-full", style.dot)} />
            )}
            {leaving == null ? (
              style.label
            ) : (
              // The two labels share one cell, so the chip holds the wider one's width while they cross.
              <span className="grid">
                <span aria-hidden="true" className="animate-status-out col-start-1 row-start-1">
                  {(STATUS_STYLES[leaving] ?? STATUS_STYLES.draft).label}
                </span>
                <span key={current} className="animate-status-in col-start-1 row-start-1">
                  {style.label}
                </span>
              </span>
            )}
            {lockedReason ? (
              <>
                <CONCEPT_ICONS.locked className="size-3 opacity-50" aria-hidden="true" />
                <span id={reasonId} className="sr-only">{lockedReason}</span>
              </>
            ) : (
              <ChevronDown className="size-3 opacity-50" />
            )}
          </button>
        }
      />
      <DropdownMenuContent
        align="start"
        className="w-44"
        onClick={(e) => e.stopPropagation()}
      >
        {APPLICATION_STATUSES.map((s) => {
          const item = STATUS_STYLES[s];
          return (
            <DropdownMenuItem
              key={s}
              onClick={() => {
                if (!pending && s !== current) onSelect(s);
              }}
            >
              <span className={cn("size-2 rounded-full", item.dot)} />
              <span className="flex-1">{item.label}</span>
              {s === current ? (
                <Check className="text-muted-foreground size-3.5" />
              ) : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
