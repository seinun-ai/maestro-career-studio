"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Loader2 } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
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

export function statusLabel(status: string | null): string {
  if (!status) return "Draft";
  return STATUS_STYLES[status as ApplicationStatus]?.label ?? "Unknown";
}

function chipClasses(interactive: boolean): string {
  return cn(
    "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-label-medium",
    interactive &&
      "cursor-pointer transition-[background-color,color,transform,box-shadow] duration-(--duration-short3) ease-(--ease-standard) select-none " +
        "hover:shadow-level1 active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring",
  );
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
  { label: string; className: string }
> = {
  pending_review: { label: "Proposed", className: "bg-primary-container text-on-primary-container" },
  needs_decision: NEEDS_YOU,
  needs_human: NEEDS_YOU,
  accepted: { label: "Queued", className: "bg-secondary-container text-on-secondary-container" },
  approved: { label: "Approved", className: "bg-success-container text-on-success-container" },
  submitted: { label: "Applied", className: "bg-success-container text-on-success-container" },
  submission_uncertain: { label: "Check if sent", className: "bg-attention-container text-on-attention-container" },
  rejected: { label: "Skipped", className: "text-muted-foreground bg-muted" },
  expired: { label: "Expired", className: "text-muted-foreground bg-muted" },
};

/** Label-only view, for callers that bring their own container. */
export function proposalStatusLabel(status: string): string {
  return PROPOSAL_STATUS_CHIP[status]?.label ?? "Unknown";
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
  className,
}: {
  status: string | null;
  onSelect: (status: ApplicationStatus) => void;
  pending?: boolean;
  className?: string;
}) {
  const current = (status ?? "draft") as ApplicationStatus;
  const style = STATUS_STYLES[current] ?? STATUS_STYLES.draft;

  // One soft ring pulse once a change has settled: not on first paint, and not
  // when a failed PATCH rolls the status back to what it was before.
  const settled = useRef(current);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (pending || settled.current === current) return;
    settled.current = current;
    setConfirm(true);
    const t = window.setTimeout(() => setConfirm(false), 400);
    return () => window.clearTimeout(t);
  }, [current, pending]);
  // A natively disabled trigger cannot take focus back when the menu closes, so
  // the chip stays focusable (aria-disabled) and just refuses to open meanwhile.
  const [open, setOpen] = useState(false);

  return (
    <DropdownMenu
      open={open && !pending}
      onOpenChange={(next) => {
        if (!pending) setOpen(next);
      }}
    >
      <DropdownMenuTrigger
        render={
          // data-status-chip: what a list hands focus to when a status change
          // removes this chip's row (the next row's chip).
          <button
            type="button"
            data-status-chip
            aria-disabled={pending || undefined}
            data-confirm={confirm || undefined}
            aria-label={`Status: ${style.label}. Change status`}
            className={cn(chipClasses(true), style.chip, "data-confirm:animate-confirm", className)}
            onClick={(e) => e.stopPropagation()}
          >
            {pending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <span className={cn("size-1.5 rounded-full", style.dot)} />
            )}
            {style.label}
            <ChevronDown className="size-3 opacity-50" />
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
