"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { SelectionBar } from "@/components/selection-bar";
import { StatusDot, statusLabel } from "@/components/status-chip";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch, promoteJobToAgentQueue } from "@/lib/api";
import { couldnt, isPlainSentence } from "@/lib/error-text";
import { isSyncQueued } from "@/lib/job-ownership";
import { APPLICATION_STATUSES, type ApplicationStatus } from "@/lib/types";

/**
 * What a picked Jobs row lets the bar do: the actions its own controls offer, under the same ownership locks.
 * There is no archive and no bulk endpoint for jobs or applications, so each one is the row's own request, sent
 * one row at a time (as the Agent inbox's Delete is): the status chip's PATCH, the Queue in Agent inbox, and
 * the row menu's Delete job or Delete application.
 */
export type JobBulkAction = "status" | "queue" | "deleteJob" | "deleteApp";

/** What the bar offers for a pick: an action only when every picked row allows it. */
export type JobBulkCan = { status: boolean; queue: boolean; delete: "deleteJob" | "deleteApp" | null };

export function bulkCan(picked: readonly (readonly JobBulkAction[])[]): JobBulkCan {
  const all = (action: JobBulkAction) => picked.length > 0 && picked.every((a) => a.includes(action));
  return {
    status: all("status"),
    queue: all("queue"),
    delete: all("deleteJob") ? "deleteJob" : all("deleteApp") ? "deleteApp" : null,
  };
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** One toast for the rows a loop could not change, with the server's reason when it is a sentence for you. */
function failedToast(verb: string, failed: unknown[], total: number) {
  if (failed.length === 0) return;
  const sample = failed[0] instanceof Error ? failed[0].message : "";
  const why = isPlainSentence(sample) ? sample : "Try again.";
  toast.error(`Couldn't ${verb} ${failed.length} of ${total}. ${why}`);
}

/**
 * The bar's three actions. Each runs once per press (useSingleFlight) and reports the rows it changed through
 * `onDone`, so the page can end Select mode; a failed or cancelled run calls nothing.
 */
export function useJobBulkActions({ onDone, returnFocus }: {
  onDone: () => void;
  /** Where focus goes once a confirmed delete closes its dialog (the bar goes with it). */
  returnFocus: () => HTMLElement | null;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();

  const setStatus = useMutation({
    mutationFn: async ({ ids, status }: { ids: string[]; status: ApplicationStatus }) => {
      let done = 0;
      let sent = 0;
      const failed: unknown[] = [];
      for (const id of ids) {
        try {
          const result = await apiFetch<unknown>(`/api/applications/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ status }),
          });
          // A job on the other copy takes the change at the next sync (202).
          if (isSyncQueued(result)) sent += 1;
          else done += 1;
        } catch (err) {
          failed.push(err);
        }
      }
      return { done, sent, failed, total: ids.length, status };
    },
    onSuccess: ({ done, sent, failed, total, status }) => {
      if (done > 0) toast.success(`Moved ${plural(done, "application", "applications")} to ${statusLabel(status)}`);
      if (sent > 0) toast.success("Sent at the next sync");
      failedToast("change the status of", failed, total);
      if (done + sent > 0) onDone();
    },
    onError: (err: Error) => toast.error(couldnt("change the status", err)),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["job-detail"] });
    },
  });

  const queue = useMutation({
    mutationFn: async (jobIds: string[]) => {
      let done = 0;
      const failed: unknown[] = [];
      for (const jobId of jobIds) {
        try {
          await promoteJobToAgentQueue(jobId);
          done += 1;
        } catch (err) {
          failed.push(err);
        }
      }
      return { done, failed, total: jobIds.length };
    },
    onSuccess: ({ done, failed, total }) => {
      if (done > 0) toast.success(`Queued ${plural(done, "job", "jobs")} in your Agent inbox.`);
      failedToast("queue", failed, total);
      if (done > 0) onDone();
    },
    onError: (err: Error) => toast.error(couldnt("queue the jobs", err)),
    // Whatever happened, a proposal may now exist (filed, then the accept failed): show it.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
      void qc.invalidateQueries({ queryKey: ["proposals"] });
    },
  });

  // One confirm for the rows picked, then one DELETE at a time, as the Agent inbox's Delete does.
  const remove = useMutation({
    mutationFn: async ({ ids, kind }: { ids: string[]; kind: "saved" | "application" }) => {
      const one = ids.length === 1;
      let confirmed = false;
      confirmed = await confirm({
        title: kind === "saved"
          ? (one ? "Delete this job?" : `Delete ${ids.length} jobs?`)
          : (one ? "Delete this application?" : `Delete ${ids.length} applications?`),
        description: kind === "saved"
          ? (one ? "This deletes the job and everything saved with it." : "This deletes the jobs and everything saved with them.")
          : (one
            ? "This deletes its tailored resume, answers and PDF. The job stays saved."
            : "This deletes their tailored resumes, answers and PDFs. The jobs stay saved."),
        confirmLabel: "Delete",
        destructive: true,
        returnFocus: () => (confirmed ? returnFocus() : null),
      });
      if (!confirmed) return null;
      let done = 0;
      const failed: unknown[] = [];
      for (const id of ids) {
        try {
          await apiFetch<void>(kind === "saved" ? `/api/jobs/${id}` : `/api/applications/${id}`, { method: "DELETE" });
          done += 1;
        } catch (err) {
          failed.push(err);
        }
      }
      return { done, failed, total: ids.length, kind };
    },
    onSuccess: (result) => {
      if (!result) return;
      const { done, failed, total, kind } = result;
      if (done > 0) {
        toast.success(`Deleted ${kind === "saved" ? plural(done, "job", "jobs") : plural(done, "application", "applications")}`);
        onDone();
      }
      failedToast("delete", failed, total);
    },
    onError: (err: Error) => toast.error(couldnt("delete them", err)),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  return {
    setStatus: useSingleFlight(setStatus.mutate),
    queue: useSingleFlight(queue.mutate),
    remove: useSingleFlight(remove.mutate),
    // The action that runs: its button spins, and every other one waits.
    running: setStatus.isPending ? "status" : queue.isPending ? "queue" : remove.isPending ? "delete" : null,
  } as const;
}

/** Jobs' Select-mode bar: Change status, Queue in Agent inbox and Delete, each only when every pick allows it.
 *  None is filled: a list view keeps its one filled button for the page. */
export function JobsBulkBar({
  selectedCount,
  can,
  running,
  onStatus,
  onQueue,
  onDelete,
  onDone,
}: {
  selectedCount: number;
  can: JobBulkCan;
  /** The action that runs, if any: its button spins and the others wait, focusable and dimmed. */
  running: "status" | "queue" | "delete" | null;
  onStatus: (status: ApplicationStatus) => void;
  onQueue: () => void;
  onDelete: () => void;
  onDone: () => void;
}) {
  const nothingFits = selectedCount > 0 && !can.status && !can.queue && !can.delete;
  const pending = running !== null;
  const waits = "data-disabled:pointer-events-none data-disabled:opacity-50";
  return (
    <SelectionBar
      selectedCount={selectedCount}
      nothingFits={nothingFits}
      hint="No one action fits all of these. Pick saved jobs or applications, not both."
      pending={pending}
      onDone={onDone}
    >
      {can.status ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={waits}
                pending={running === "status"}
                disabled={pending}
                focusableWhenDisabled
              >
                Change status
                <ChevronDown aria-hidden="true" />
              </Button>
            }
          />
          <DropdownMenuContent align="start" side="top" className="w-max">
            {APPLICATION_STATUSES.map((status) => (
              <DropdownMenuItem key={status} onClick={() => onStatus(status)}>
                <StatusDot status={status} />
                {statusLabel(status)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {can.queue ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={waits}
          onClick={onQueue}
          pending={running === "queue"}
          disabled={pending}
          focusableWhenDisabled
        >
          Queue in Agent inbox
        </Button>
      ) : null}
      {can.delete ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={waits}
          onClick={onDelete}
          pending={running === "delete"}
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
