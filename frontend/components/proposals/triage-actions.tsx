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
import { apiFetch } from "@/lib/api";
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

// Display-only rename. The VALUE stays "declined by user" because it is sent as
// the API `reason` field and read back verbatim by list_proposals/get_proposal —
// an agent-visible vocabulary. Only the label follows the Skip/Skipped wording.
const REASON_LABEL: Partial<Record<(typeof DECLINE_REASONS)[number], string>> = {
  "declined by user": "skipped by you",
};

type BulkStatus = "accepted" | "rejected";

export function useProposalActions() {
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
    }: {
      id: string;
      status: Extract<ProposalStatus, "accepted" | "rejected">;
      reason?: string;
    }) =>
      apiFetch<Proposal>(`/api/proposals/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          consent: { channel: "frontend" },
          ...(reason ? { reason } : {}),
        }),
      }),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
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
      const failed = data.results.filter((r) => !r.ok);
      if (failed.length === 0) return;
      const verb =
        vars.status === "accepted" ? "accepted" : "skipped";
      const sample = failed[0]?.detail ?? "already terminal";
      toast.error(
        `${failed.length} of ${vars.ids.length} could not be ${verb} — ${sample}`,
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      const ok = await confirm({
        title: "Delete this proposal?",
        description:
          "Its evidence screenshots are removed. Submitted proposals cannot be deleted.",
        confirmLabel: "Delete",
        destructive: true,
      });
      if (!ok) return false;
      await apiFetch<void>(`/api/proposals/${id}`, { method: "DELETE" });
      return true;
    },
    onSuccess: (didDelete) => {
      if (!didDelete) return;
      toast.success("Proposal deleted");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return { transition, bulk, remove };
}

export function DeclineDialog({
  open,
  onOpenChange,
  onConfirm,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => void;
  pending?: boolean;
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
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Skip this posting?</DialogTitle>
          <DialogDescription>
            Skips only this posting. The company is not affected.
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
              {REASON_LABEL[reason] ?? reason}
            </label>
          ))}
        </fieldset>
        <div className="grid gap-1.5">
          <Label htmlFor="decline-override">
            Custom reason <span className="text-muted-foreground">· optional</span>
          </Label>
          <Input
            id="decline-override"
            placeholder="e.g. hiring freeze announced"
            value={override}
            onChange={(e) => setOverride(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={submit}
            disabled={pending}
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
  onAccept,
  onDecline,
  onClear,
  pending,
}: {
  selectedCount: number;
  onAccept: () => void;
  onDecline: () => void;
  onClear: () => void;
  pending?: boolean;
}) {
  if (selectedCount <= 0) return null;

  return (
    <div className="bg-background/95 supports-backdrop-filter:backdrop-blur-sm fixed inset-x-0 bottom-0 z-40 border-t px-4 py-3">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-2">
        <span className="text-sm font-medium tabular-nums">
          {selectedCount} selected
        </span>
        <Button
          type="button"
          size="sm"
          className="rounded-full"
          onClick={onAccept}
          disabled={pending}
        >
          Accept
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="rounded-full"
          onClick={onDecline}
          disabled={pending}
        >
          Skip
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="rounded-full"
          onClick={onClear}
          disabled={pending}
        >
          Clear
        </Button>
      </div>
    </div>
  );
}
