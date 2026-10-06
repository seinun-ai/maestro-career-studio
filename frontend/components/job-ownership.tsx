"use client";

import { useId } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Laptop } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { LoadErrorState } from "@/components/load-error-state";
import { isLoadFailure, type LoadQuery } from "@/lib/query-state";
import { Button } from "@/components/ui/button";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
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
    },
    onError: (error: Error) => toast.error(couldnt("change where you work on this job", error)),
  });
}

export function JobOwnershipMark({ jobId, ownership }: { jobId: string; ownership?: JobOwnership }) {
  const view = jobOwnershipView(ownership);
  const mutation = useOwnershipAction(jobId);
  const act = useSingleFlight(mutation.mutate);
  if (!view.mark) return null;
  const Icon = ownership?.owner === "bot" ? Bot : Laptop;
  return (
    <div className="flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
      <Badge variant="secondary"><Icon className="size-3" aria-hidden="true" />{view.mark}</Badge>
      {view.action ? (
        <Button size="xs" variant="outline" disabled={mutation.isPending} onClick={() => act(view.action!)}>
          {view.action === "keep-here" ? "Keep it here" : "Work on it here"}
        </Button>
      ) : null}
      {view.pending ? <span role="status" className="text-muted-foreground text-body-small">Sent at the next sync</span> : null}
    </div>
  );
}

export function JobOwnershipNotice({ ownership }: { ownership?: JobOwnership }) {
  const id = useId();
  const { reason } = jobOwnershipView(ownership);
  return reason ? <p id={id} className="text-muted-foreground text-body-small">{reason}</p> : null;
}

export function JobOwnershipLoadError({ query }: {
  query: LoadQuery & { isFetching: boolean; refetch: () => unknown };
}) {
  return isLoadFailure(query) ? (
    <LoadErrorState title="Couldn't load where these jobs are being worked on."
      retrying={query.isFetching} onRetry={() => { void query.refetch(); }} />
  ) : null;
}
