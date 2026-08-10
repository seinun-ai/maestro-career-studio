"use client";

import { Check, ChevronDown, Loader2 } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { APPLICATION_STATUSES, type ApplicationStatus } from "@/lib/types";

/** Tonal chip colors per status — soft fill + strong dot, both themes. */
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
    chip: "bg-blue-600/10 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
    dot: "bg-blue-600 dark:bg-blue-400",
  },
  interviewing: {
    label: "Interviewing",
    chip: "bg-amber-500/15 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300",
    dot: "bg-amber-500 dark:bg-amber-400",
  },
  offered: {
    label: "Offer",
    chip: "bg-violet-600/10 text-violet-700 dark:bg-violet-400/15 dark:text-violet-300",
    dot: "bg-violet-600 dark:bg-violet-400",
  },
  accepted: {
    label: "Accepted",
    chip: "bg-green-600/10 text-green-700 dark:bg-green-400/15 dark:text-green-300",
    dot: "bg-green-600 dark:bg-green-400",
  },
  rejected: {
    label: "Rejected",
    chip: "bg-red-600/10 text-red-700 dark:bg-red-400/15 dark:text-red-300",
    dot: "bg-red-600 dark:bg-red-400",
  },
  withdrawn: {
    label: "Withdrawn",
    chip: "bg-muted text-muted-foreground line-through decoration-muted-foreground/40",
    dot: "bg-muted-foreground/40",
  },
};

export function statusLabel(status: string | null): string {
  if (!status) return "Draft";
  return STATUS_STYLES[status as ApplicationStatus]?.label ?? status;
}

function chipClasses(interactive: boolean): string {
  return cn(
    "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium",
    interactive &&
      "cursor-pointer transition-[transform,box-shadow] duration-150 ease-out select-none " +
        "hover:shadow-sm active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-ring/60",
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
 * `AGENT_LANE_LABELS` in the Applications filter already says exactly that.
 * The four states the tracker never renders (approved, submitted,
 * submission_uncertain) keep their literal names.
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
  pending_review: { label: "Proposed", className: "bg-blue-500/10 text-blue-700 dark:text-blue-400" },
  needs_decision: { label: "Needs you", className: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
  needs_human: { label: "Needs you", className: "bg-orange-500/10 text-orange-700 dark:text-orange-400" },
  accepted: { label: "Queued", className: "bg-sky-500/10 text-sky-700 dark:text-sky-400" },
  approved: { label: "Approved", className: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
  submitted: { label: "Submitted", className: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300" },
  submission_uncertain: { label: "Submission uncertain", className: "bg-orange-500/10 text-orange-700 dark:text-orange-400" },
  rejected: { label: "Skipped", className: "text-muted-foreground bg-muted" },
  expired: { label: "Expired", className: "text-muted-foreground bg-muted" },
};

/** Label-only view, for callers that bring their own container. */
export function proposalStatusLabel(status: string): string {
  return PROPOSAL_STATUS_CHIP[status]?.label ?? status;
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

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            aria-label={`Status: ${style.label}. Change status`}
            className={cn(chipClasses(true), style.chip, className)}
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
                if (s !== current) onSelect(s);
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
