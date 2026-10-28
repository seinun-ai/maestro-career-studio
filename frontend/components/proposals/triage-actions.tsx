"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { SelectionBar } from "@/components/selection-bar";
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
import { isSyncQueued } from "@/lib/job-ownership";
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
  /** A Queue or Skip waits this long before the lists refetch, so the row it removes can leave first. */
  settleMs?: number;
  onDone?: (ids: string[], became: BulkStatus | "pending_review" | "deleted") => void;
  onUndone?: () => void;
  onQueued?: (ids: string[]) => void;
};

export function useProposalActions(events: ProposalActionEvents = {}) {
  const qc = useQueryClient();
  const confirm = useConfirm();

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: PROPOSALS_KEY });
    void qc.invalidateQueries({ queryKey: FUNNEL_KEY });
    void qc.invalidateQueries({ queryKey: ["job-detail"] });
    void qc.invalidateQueries({ queryKey: ["proposal"] });
    void qc.invalidateQueries({ queryKey: ["jobs"] });
    void qc.invalidateQueries({ queryKey: ["today"] });
  };

  // A row that is leaving is still in the lists until the refetch, so a caller with an exit asks for a pause.
  const settle = () => {
    if (events.settleMs) setTimeout(invalidate, events.settleMs);
    else invalidate();
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
      // Sent to the copy that owns the job (202): nothing changed here yet, so the row stays and refetches now.
      if (isSyncQueued(_data)) {
        invalidate();
        toast.success("Sent at the next sync");
        events.onQueued?.([vars.id]);
        events.onUndone?.();
        return;
      }
      if (vars.status === "pending_review") invalidate();
      else settle();
      // One owner for the words: the inbox and the job page say the same thing.
      if (vars.status === "accepted") toast.success("Queued. A connected agent can apply to it now.");
      else if (vars.status === "rejected") toast.success("Proposal skipped");
      else toast.success("Kept. It's back in To review.");
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
      const failed = data.results.filter((r) => !r.ok);
      const failedIds = new Set(failed.map((r) => r.id));
      // Rows sent to the copy that owns their job (202) change at the next sync: they stay put meanwhile.
      const queued = data.results.filter((r) => r.ok && r.detail === "Sent at the next sync.").map((r) => r.id);
      const done = vars.ids.filter((id) => !failedIds.has(id) && !queued.includes(id));
      if (done.length > 0) settle();
      else invalidate();
      // Only the rows that changed leave the selection and the list; a failed one stays to retry.
      if (queued.length > 0) {
        toast.success("Sent at the next sync");
        events.onQueued?.(queued);
        events.onUndone?.();
        if (done.length > 0) events.onDone?.(done, vars.status);
      } else {
        events.onDone?.(done, vars.status);
      }
      if (failed.length === 0) {
        const n = done.length;
        if (n > 0) toast.success(`${vars.status === "accepted" ? "Queued" : "Skipped"} ${n} ${n === 1 ? "proposal" : "proposals"}`);
        return;
      }
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

  // The bar's Delete: one confirm for the rows picked, then one DELETE at a time (the server writes one
  // row at a time anyway). Rows that go leave the selection; a refused one stays, named in one toast.
  const removeMany = useMutation({
    mutationFn: async ({ ids, next }: { ids: string[]; next?: () => HTMLElement | null }) => {
      let confirmed = false;
      confirmed = await confirm({
        title: ids.length === 1 ? "Delete this proposal?" : `Delete ${ids.length} proposals?`,
        description: "This also deletes the screenshots your agents took.",
        confirmLabel: "Delete",
        destructive: true,
        returnFocus: () => (confirmed && next ? next() : null),
      });
      if (!confirmed) return null;
      const done: string[] = [];
      const failed: unknown[] = [];
      for (const id of ids) {
        try {
          await apiFetch<void>(`/api/proposals/${id}`, { method: "DELETE" });
          done.push(id);
        } catch (err) {
          failed.push(err);
        }
      }
      return { done, failed, total: ids.length };
    },
    onSuccess: (result) => {
      if (!result) {
        events.onUndone?.();
        return;
      }
      invalidate();
      const { done, failed, total } = result;
      if (done.length > 0) {
        toast.success(`Deleted ${done.length} ${done.length === 1 ? "proposal" : "proposals"}`);
        events.onDone?.(done, "deleted");
      } else {
        events.onUndone?.();
      }
      if (failed.length > 0) {
        const sample = failed[0] instanceof Error ? failed[0].message : "";
        const why = isPlainSentence(sample) ? sample : "Try again.";
        toast.error(`Couldn't delete ${failed.length} of ${total}. ${why}`);
      }
    },
    onError: (err: Error) => {
      toast.error(couldnt("delete the proposals", err));
      events.onUndone?.();
    },
  });

  // One request per click: `isPending` disables the buttons a render too late, so a double click on a
  // row's Queue sent two PATCHes, the second "cannot go accepted -> accepted". The raw mutations stay here.
  const transitionOnce = useSingleFlight(transition.mutate);
  const bulkOnce = useSingleFlight(bulk.mutate);
  const removeOnce = useSingleFlight(remove.mutate);
  const removeManyOnce = useSingleFlight(removeMany.mutate);
  // The rows in flight, for a spinner on each: the buttons stay locked everywhere, but only these rows ask.
  const actingIds = new Set<string>(
    transition.isPending && transition.variables ? [transition.variables.id]
    : bulk.isPending && bulk.variables ? bulk.variables.ids
    : [],
  );
  return {
    transition: transitionOnce,
    bulk: bulkOnce,
    remove: removeOnce,
    removeMany: removeManyOnce,
    // Any of them running: every triage control waits, focusable and dimmed.
    pending: transition.isPending || bulk.isPending || remove.isPending || removeMany.isPending,
    // Only the bulk Queue spins: a bulk Skip runs from the dialog, whose own button spins.
    queuePending: bulk.isPending && bulk.variables?.status === "accepted",
    actingIds,
  };
}

export function DeclineDialog({
  open,
  onOpenChange,
  onConfirm,
  pending,
  blocked,
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => void;
  pending?: boolean;
  /** A chosen job is on the other copy: Skip waits, Cancel still closes. */
  blocked?: boolean;
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
              className="flex items-center gap-2 text-body-medium"
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
            pending={pending}
            disabled={blocked}
          >
            Skip
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export type BulkActions = { queue: boolean; skip: boolean; delete: boolean };

/**
 * The Agent inbox's Select-mode bar (`SelectionBar`, shared with Jobs). It offers only what every picked row
 * allows, the same actions each row's own buttons offer; a mixed pick says so. Queue is its one filled button.
 */
export function BulkBar({
  selectedCount,
  can,
  onQueue,
  onDecline,
  onDelete,
  onDone,
  pending,
  queuePending,
}: {
  selectedCount: number;
  can: BulkActions;
  onQueue: () => void;
  onDecline: () => void;
  onDelete: () => void;
  onDone: () => void;
  /** Any triage action runs: every button waits, focusable and dimmed. */
  pending?: boolean;
  /** The bulk Queue itself runs: its button spins. */
  queuePending?: boolean;
}) {
  const nothingFits = selectedCount > 0 && !can.queue && !can.skip && !can.delete;
  return (
    <SelectionBar
      selectedCount={selectedCount}
      nothingFits={nothingFits}
      hint="No one action fits all of these. Pick jobs from one lane."
      pending={pending}
      onDone={onDone}
    >
      {can.queue ? (
        <Button
          type="button"
          size="sm"
          onClick={onQueue}
          pending={queuePending}
          disabled={pending}
          focusableWhenDisabled
        >
          Queue
        </Button>
      ) : null}
      {can.skip ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onDecline}
          disabled={pending}
          focusableWhenDisabled
        >
          Skip
        </Button>
      ) : null}
      {can.delete ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onDelete}
          disabled={pending}
          focusableWhenDisabled
        >
          <Trash2 aria-hidden="true" />
          Delete
        </Button>
      ) : null}
    </SelectionBar>
  );
}
