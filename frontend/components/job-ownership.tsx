"use client";

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { REQUEST_QUEUED, jobOwnershipView, syncActionMessage, type OwnershipActionName } from "@/lib/job-ownership";
import type { JobOwnership } from "@/lib/types";

const ACTION_LABEL = { "keep-here": "Keep it here", "work-here": "Work on it here" } as const;

/** One key for a job's ownership request, so every button for it (a header's, a row menu's) reads one state. */
const ownershipKey = (jobId: string) => ["job-ownership", jobId];

/** True while a request to move this job is in flight, wherever on screen it was started. */
function useOwnershipBusy(jobId: string): boolean {
  return useIsMutating({ mutationKey: ownershipKey(jobId) }) > 0;
}

function useOwnershipAction(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ownershipKey(jobId),
    mutationFn: (action: OwnershipActionName) => apiFetch(`/api/jobs/${jobId}/${action}`, { method: "POST" }),
    onSuccess: (result) => {
      toast.success(syncActionMessage(result, "Kept on your laptop"));
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      void qc.invalidateQueries({ queryKey: ["proposals"] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (error: Error) => toast.error(couldnt("change where you work on this job", error)),
  });
}

export function JobOwnershipMark({ jobId, ownership }: { jobId: string; ownership?: JobOwnership }) {
  const view = jobOwnershipView(ownership);
  const mutation = useOwnershipAction(jobId);
  const act = useSingleFlight(mutation.mutate);
  const busy = useOwnershipBusy(jobId);
  if (!view.mark) return null;
  // The bot is where your connected agents run, so it wears their glyph; the laptop has its own.
  const Icon = ownership?.owner === "bot" ? CONCEPT_ICONS.agentInbox : CONCEPT_ICONS.laptop;
  return (
    <div className="flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
      <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground">
        <Icon className="size-3 shrink-0" aria-hidden="true" />
        {view.mark}
      </span>
      {view.action ? (
        <Button size="xs" variant="outline" pending={busy} onClick={() => act(view.action!)}>
          {ACTION_LABEL[view.action]}
        </Button>
      ) : null}
      {view.pending ? <span role="status" className="text-muted-foreground text-body-small">{REQUEST_QUEUED}</span> : null}
    </div>
  );
}

/** The row menu's "Work on it here" / "Keep it here". A menu closes on click, so the request's progress
 * is read from the query client: reopening the menu mid-request finds the item disabled. A request of
 * yours that is still waiting for the next sync disables it too, so no second one goes out. */
export function OwnershipMenuItem({ jobId, action, pending }: { jobId: string; action: OwnershipActionName; pending: boolean }) {
  const mutation = useOwnershipAction(jobId);
  const act = useSingleFlight(mutation.mutate);
  const busy = useOwnershipBusy(jobId);
  const Icon = CONCEPT_ICONS.laptop;
  return (
    <DropdownMenuItem disabled={busy || pending} onClick={() => act(action)}>
      <Icon className="size-4" aria-hidden="true" />
      {pending ? REQUEST_QUEUED : ACTION_LABEL[action]}
    </DropdownMenuItem>
  );
}

export function JobOwnershipNotice({ ownership }: { ownership?: JobOwnership }) {
  const { reason } = jobOwnershipView(ownership);
  if (!reason) return null;
  return (
    <p className="text-muted-foreground flex items-start gap-1.5 text-body-small">
      <CONCEPT_ICONS.locked className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{reason}</span>
    </p>
  );
}
