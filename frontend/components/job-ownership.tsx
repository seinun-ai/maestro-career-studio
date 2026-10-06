"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { jobOwnershipView, syncActionMessage } from "@/lib/job-ownership";
import type { JobOwnership } from "@/lib/types";

function useOwnershipAction(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: string) => apiFetch(`/api/jobs/${jobId}/${action}`, { method: "POST" }),
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
        <Button size="xs" variant="outline" pending={mutation.isPending} onClick={() => act(view.action!)}>
          {view.action === "keep-here" ? "Keep it here" : "Work on it here"}
        </Button>
      ) : null}
      {view.pending ? <span role="status" className="text-muted-foreground text-body-small">Sent at the next sync</span> : null}
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
