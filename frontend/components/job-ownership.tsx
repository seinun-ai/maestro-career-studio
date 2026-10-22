"use client";

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { REQUEST_QUEUED, jobOwnershipView, ownershipSays, syncActionMessage, type OwnershipActionName } from "@/lib/job-ownership";
import type { JobOwnership } from "@/lib/types";

const ACTION_LABEL = { "keep-here": "Keep it here", "work-here": "Work on it here" } as const;

/** One key for a job's ownership request, so every button for it (a header's, a row's pop-up) reads one state. */
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

/** Ask to move this job, once per press; `busy` while any request for it is in flight, wherever it started. */
function useOwnershipRequest(jobId: string) {
  const mutation = useOwnershipAction(jobId);
  const act = useSingleFlight(mutation.mutate);
  const busy = useOwnershipBusy(jobId);
  return { act, busy };
}

/** The request's button (Keep it here, Work on it here) and, once one is queued, that it goes at the next sync. */
function OwnershipRequest({
  view,
  act,
  busy,
}: {
  view: ReturnType<typeof jobOwnershipView>;
  act: (action: OwnershipActionName) => void;
  busy: boolean;
}) {
  return (
    <>
      {view.action ? (
        <Button size="xs" variant="outline" pending={busy} onClick={() => act(view.action!)}>
          {ACTION_LABEL[view.action]}
        </Button>
      ) : null}
      {view.pending ? <span role="status" className="text-muted-foreground text-body-small">{REQUEST_QUEUED}</span> : null}
    </>
  );
}

export function JobOwnershipMark({ jobId, ownership }: { jobId: string; ownership?: JobOwnership }) {
  const view = jobOwnershipView(ownership);
  const request = useOwnershipRequest(jobId);
  if (!view.mark) return null;
  // The bot is where your connected agents run, so it wears their glyph; the laptop has its own.
  const Icon = ownership?.owner === "bot" ? CONCEPT_ICONS.agentInbox : CONCEPT_ICONS.laptop;
  return (
    <div className="flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
      <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-surface-container px-2 text-label-medium text-foreground">
        <Icon className="size-3 shrink-0" aria-hidden="true" />
        {view.mark}
      </span>
      <OwnershipRequest view={view} {...request} />
    </div>
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

/** A list row's ownership, kept off the row: one small icon opens why the job is locked, its request and
 * that request's progress. Nothing to say (your laptop's job, nothing waiting): nothing drawn. */
export function JobOwnershipPopover({ jobId, ownership }: { jobId: string; ownership?: JobOwnership }) {
  const view = jobOwnershipView(ownership);
  const request = useOwnershipRequest(jobId);
  if (!ownershipSays(ownership)) return null;
  const Icon = view.reason ? CONCEPT_ICONS.locked : ownership?.owner === "bot" ? CONCEPT_ICONS.agentInbox : CONCEPT_ICONS.laptop;
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="relative text-muted-foreground"
            aria-label={view.pending ? `Where this job is, ${REQUEST_QUEUED.toLowerCase()}` : "Where this job is"}
          />
        }
      >
        <Icon className="size-3.5" aria-hidden="true" />
        {view.pending ? <span className="absolute top-1 right-1 size-1.5 rounded-full bg-primary" aria-hidden="true" /> : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="flex max-w-72 flex-col items-start gap-2">
        <p className="text-body-small">{view.reason ?? view.mark}</p>
        <OwnershipRequest view={view} {...request} />
      </PopoverContent>
    </Popover>
  );
}
