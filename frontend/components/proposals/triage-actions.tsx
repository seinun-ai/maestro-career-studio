"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt, isPlainSentence } from "@/lib/error-text";
import type {
  Proposal,
  ProposalBulkResponse,
  ProposalStatus,
} from "@/lib/types";

const PROPOSALS_KEY = ["proposals"] as const;
const FUNNEL_KEY = ["proposals", "funnel"] as const;

const DECLINE_REASONS = [
  "declined by user",
  "no longer relevant",
  "position closed",
  "duplicate",
] as const;

// Display only. The VALUES stay as they are because they are sent as the API
// `reason` field and read back verbatim by list_proposals/get_proposal: an
// agent-visible vocabulary. "skipped by you" as a reason for skipping was circular.
const REASON_LABEL: Record<(typeof DECLINE_REASONS)[number], string> = {
  "declined by user": "Not interested",
  "no longer relevant": "No longer relevant",
  "position closed": "Position closed",
  duplicate: "Duplicate",
};

/** A stored skip reason in words; a reason the user typed shows as typed. */
export function reasonLabel(reason: string): string {
  return REASON_LABEL[reason as (typeof DECLINE_REASONS)[number]] ?? reason;
}

type BulkStatus = "accepted" | "rejected";

/**
 * What a caller hears back, instead of per-call callbacks (a guarded start takes none). `onDone`: the
 * change was made, to these ids. `onUndone`: nothing changed (the request failed, or a delete was not
 * confirmed), so focus a caller moved on at the click has nowhere to go.
 */
export type ProposalActionEvents = {
  onDone?: (ids: string[], became: BulkStatus | "pending_review" | "deleted") => void;
  onUndone?: () => void;
};

export function useProposalActions(events: ProposalActionEvents = {}) {
  const qc = useQueryClient();
  const confirm = useConfirm();

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: PROPOSALS_KEY });
    void qc.invalidateQueries({ queryKey: FUNNEL_KEY });
    void qc.invalidateQueries({ queryKey: ["job-detail"] });
    void qc.invalidateQueries({ queryKey: ["proposal"] });
  };

  const transition = useMutation({
    mutationFn: ({
      id,
      status,
      reason,
      applicationId,
    }: {
      id: string;
      /** `pending_review` is Keep it on a Needs-you proposal: the agent's question answered yes. */
      status: Extract<ProposalStatus, "accepted" | "rejected" | "pending_review">;
      reason?: string;
      /** Keep it from the job page: the job's application, for a proposal linked to none. */
      applicationId?: string;
    }) =>
      apiFetch<Proposal>(`/api/proposals/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          ...(status === "pending_review" ? {} : { consent: { channel: "frontend" } }),
          ...(reason ? { reason } : {}),
          ...(applicationId ? { application_id: applicationId } : {}),
        }),
      }),
    onSuccess: (_data, vars) => {
      invalidate();
      events.onDone?.([vars.id], vars.status);
    },
    onError: (err: Error, vars) => {
      toast.error(couldnt(vars.status === "pending_review" ? "keep it" : "update the proposal", err));
      events.onUndone?.();
    },
  });

  const bulk = useMutation({
    mutationFn: ({
      ids,
      status,
      reason,
    }: {
      ids: string[];
      status: BulkStatus;
      reason?: string;
    }) =>
      apiFetch<ProposalBulkResponse>("/api/proposals/bulk-transition", {
        method: "POST",
        body: JSON.stringify({
          ids,
          status,
          consent: { channel: "frontend" },
          ...(reason ? { reason } : {}),
        }),
      }),
    onSuccess: (data, vars) => {
      invalidate();
      events.onDone?.(vars.ids, vars.status);
      const failed = data.results.filter((r) => !r.ok);
      if (failed.length === 0) return;
      // "queue": Accept's result is a Queued chip (the ONE status vocabulary).
      const verb = vars.status === "accepted" ? "queue" : "skip";
      // The server's reason, only when it is a sentence written for the user.
      const sample = failed[0]?.detail ?? "";
      const why = isPlainSentence(sample) ? sample : "Try again.";
      toast.error(`Couldn't ${verb} ${failed.length} of ${vars.ids.length}. ${why}`);
    },
    onError: (err: Error) => {
      toast.error(couldnt("update the proposals", err));
      events.onUndone?.();
    },
  });

  const remove = useMutation({
    // `next`: where focus goes once a confirmed delete takes its row, or its button, away. The
    // confirm closes before the DELETE lands, so it is read then; a cancel returns to the button.
    mutationFn: async ({ id, next }: { id: string; next?: () => HTMLElement | null }) => {
      let confirmed = false;
      confirmed = await confirm({
        title: "Delete this proposal?",
        description: "This also deletes the screenshots your agent took.",
        confirmLabel: "Delete",
        destructive: true,
        returnFocus: () => (confirmed && next ? next() : null),
      });
      if (!confirmed) return false;
      await apiFetch<void>(`/api/proposals/${id}`, { method: "DELETE" });
      return true;
    },
    onSuccess: (didDelete, { id }) => {
      if (!didDelete) {
        events.onUndone?.();
        return;
      }
      toast.success("Proposal deleted");
      invalidate();
      events.onDone?.([id], "deleted");
    },
    onError: (err: Error) => {
      toast.error(couldnt("delete the proposal", err));
      events.onUndone?.();
    },
  });

  // One request per click: `isPending` disables the buttons a render too late, so a double click on a
  // row's Queue sent two PATCHes, the second "cannot go accepted -> accepted". The raw mutations stay here.
  const transitionOnce = useSingleFlight(transition.mutate);
  const bulkOnce = useSingleFlight(bulk.mutate);
  const removeOnce = useSingleFlight(remove.mutate);
  return {
    transition: transitionOnce,
    bulk: bulkOnce,
    remove: removeOnce,
    // Any of them running: every triage control waits, focusable and dimmed.
    pending: transition.isPending || bulk.isPending || remove.isPending,
  };
}

export function DeclineDialog({
  open,
  onOpenChange,
  onConfirm,
  pending,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => void;
  pending?: boolean;
  /** Where focus goes when it closes (Base UI's `finalFocus`): a Skip takes its opener away. */
  finalFocus?: () => HTMLElement | boolean;
}) {
  const [preset, setPreset] =
    useState<(typeof DECLINE_REASONS)[number]>("declined by user");
  const [override, setOverride] = useState("");

  const submit = () => {
    const reason = override.trim() || preset;
    onConfirm(reason);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm" finalFocus={finalFocus}>
        <DialogHeader>
          <DialogTitle>Skip this job?</DialogTitle>
          <DialogDescription>
            Other jobs at this company aren&apos;t affected.
          </DialogDescription>
        </DialogHeader>
        <fieldset className="grid gap-2">
          <legend className="sr-only">Skip reason</legend>
          {DECLINE_REASONS.map((reason) => (
            <label
              key={reason}
              className="flex items-center gap-2 text-sm"
            >
              <input
                type="radio"
                name="decline-reason"
                value={reason}
                checked={preset === reason}
                onChange={() => setPreset(reason)}
                className="size-3.5 accent-primary"
              />
              {REASON_LABEL[reason]}
            </label>
          ))}
        </fieldset>
        <div className="grid gap-1.5">
          <Label htmlFor="decline-override" optional>
            Other reason
          </Label>
          <Input
            id="decline-override"
            value={override}
            onChange={(e) => setOverride(e.target.value)}
          />
        </div>
        <DialogFooter>
          {/* Focusable while the Skip runs: a natively disabled button dropped focus to <body>. */}
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={submit}
            disabled={pending}
            focusableWhenDisabled
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            Skip
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BulkBar({
  selectedCount,
  onQueue,
  onDecline,
  onClear,
  pending,
}: {
  selectedCount: number;
  onQueue: () => void;
  onDecline: () => void;
  onClear: () => void;
  pending?: boolean;
}) {
  if (selectedCount <= 0) return null;

  return (
    // data-slot: globals.css keeps a focused row above this fixed bar. Its buttons stay focusable
    // while they run, and the page hands focus on when a Queue, Skip or Clear takes the bar away.
    <div
      data-slot="bulk-bar"
      className="bg-background/95 supports-backdrop-filter:backdrop-blur-sm fixed inset-x-0 bottom-0 z-40 border-t px-4 py-3"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-2">
        <span className="text-sm font-medium tabular-nums">
          {selectedCount} selected
        </span>
        <Button
          type="button"
          size="sm"
          className="rounded-full data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onQueue}
          disabled={pending}
          focusableWhenDisabled
        >
          Queue
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="rounded-full data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onDecline}
          disabled={pending}
          focusableWhenDisabled
        >
          Skip
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="rounded-full data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onClear}
          disabled={pending}
          focusableWhenDisabled
        >
          Clear
        </Button>
      </div>
    </div>
  );
}
