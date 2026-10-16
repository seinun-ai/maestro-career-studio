"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { isSyncQueued } from "@/lib/job-ownership";

import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { JobTrackingUrlField } from "@/components/job-tracking-url-field";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { Application, JobDetail, Referral } from "@/lib/types";

function formatDateInput(value: string | null | undefined): string {
  if (!value) return "";
  return value.slice(0, 10);
}

function toIsoDate(value: string): string | null {
  if (!value) return null;
  return new Date(`${value}T00:00:00Z`).toISOString();
}

function referralLabel(referral: Referral): string {
  return referral.contact_name
    ? `${referral.company} — ${referral.contact_name}`
    : referral.company;
}

/**
 * Hook returning the patch + delete mutations for an application.
 * Used by ApplicationDetails, the header StatusChip, step 4's Mark applied, and any consumer
 * that wants to mutate.
 */
export function useApplicationMutations({
  applicationId,
  jobId,
}: {
  applicationId: string;
  jobId: string;
}) {
  const qc = useQueryClient();

  const patch = useMutation({
    mutationFn: (body: Partial<Application>) =>
      apiFetch<Application>(`/api/applications/${applicationId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    // The header chip turns at once; a failed PATCH puts the cached job back.
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["job-detail", jobId] });
      const previous = qc.getQueryData<JobDetail>(["job-detail", jobId]);
      qc.setQueryData<JobDetail>(["job-detail", jobId], (detail) =>
        detail?.application
          ? { ...detail, application: { ...detail.application, ...body } }
          : detail,
      );
      return { previous };
    },
    // A job on the other copy takes the change at the next sync (202): the refetch puts the chip back meanwhile.
    onSuccess: (result) => {
      if (isSyncQueued(result)) toast.success("Sent at the next sync");
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error, _body, context) => {
      qc.setQueryData(["job-detail", jobId], context?.previous);
      toast.error(couldnt("update the application", err));
    },
    // Returned, so isPending lasts until the refetch lands.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      return qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
    },
  });

  const deleteApp = useDeleteApplication({ applicationId, jobId });

  return { patch, deleteApp };
}

/** The application's DELETE alone: the delete confirm needs only this, not the patch's optimistic cache work. */
function useDeleteApplication({ applicationId, jobId }: { applicationId: string; jobId: string }) {
  const qc = useQueryClient();
  const router = useRouter();
  const deleteApp = useMutation({
    mutationFn: () =>
      apiFetch<void>(`/api/applications/${applicationId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      toast.success("Application deleted");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      router.push(`/jobs/${jobId}`);
    },
    onError: (err: Error) => toast.error(couldnt("delete the application", err)),
  });
  return deleteApp;
}

/** Delete application with its confirm, for step 4's Application details and step 3's ⋯ (one sentence, one request). */
export function useConfirmDeleteApplication({
  applicationId,
  jobId,
  returnFocus,
}: {
  applicationId: string;
  jobId: string;
  returnFocus?: () => HTMLElement | null;
}) {
  const confirm = useConfirm();
  const deleteApp = useDeleteApplication({ applicationId, jobId });
  const onDelete = async () => {
    const ok = await confirm({
      title: "Delete this application?",
      description:
        "This deletes its tailored resume, answers and PDF. The job stays saved.",
      confirmLabel: "Delete",
      destructive: true,
      returnFocus,
    });
    if (!ok) return;
    deleteApp.mutate();
  };
  return { onDelete, deleting: deleteApp.isPending };
}

/**
 * The application's details, inline under step 4's Application details disclosure: applied date, tracking URL,
 * referral, notes and Delete application. Status is NOT here: it lives in the header's StatusChip and step 4's
 * Mark applied. Mounted only while the disclosure is open, unlike Settings' disclosures, which hide and keep
 * their drafts: each open reseeds the fields from the server, so a stale local note can never overwrite one an
 * agent wrote meanwhile (a blur saves before the toggle's click closes it), and the referrals are read only then.
 * A blur saves only a field that changed.
 */
export function ApplicationDetails({
  app,
  jobId,
  jobSourceUrl,
  readOnly = false,
  canRequest = true,
}: {
  app: Application;
  jobId: string;
  jobSourceUrl?: string | null;
  readOnly?: boolean;
  canRequest?: boolean;
}) {
  const appliedId = useId();
  const referralId = useId();
  const notesId = useId();
  const { patch } = useApplicationMutations({
    applicationId: app.id,
    jobId,
  });
  const { onDelete, deleting } = useConfirmDeleteApplication({ applicationId: app.id, jobId });
  const { data: referrals } = useQuery({
    queryKey: ["referrals"],
    queryFn: () => apiFetch<Referral[]>("/api/referrals"),
  });

  const onPatch = (body: Partial<Application>) => {
    if (readOnly && (!canRequest || Object.keys(body).some((key) => key !== "notes"))) return;
    patch.mutate(body);
  };

  const [appliedAt, setAppliedAt] = useState(formatDateInput(app.applied_at));
  // Mark applied (or the status chip) stamps the date while this is open: the field follows it.
  const [appliedSeen, setAppliedSeen] = useState(app.applied_at);
  if (app.applied_at !== appliedSeen) {
    setAppliedSeen(app.applied_at);
    setAppliedAt(formatDateInput(app.applied_at));
  }
  const [notes, setNotes] = useState(app.notes ?? "");

  return (
    <div className="grid max-w-md gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor={appliedId} className="text-label-medium">
          Applied on
        </Label>
        <Input
          id={appliedId}
          type="date"
          className="h-8 w-44 text-body-medium"
          value={appliedAt}
          disabled={readOnly}
          onChange={(e) => setAppliedAt(e.target.value)}
          onBlur={() => {
            if (appliedAt !== formatDateInput(app.applied_at)) onPatch({ applied_at: toIsoDate(appliedAt) });
          }}
        />
      </div>

      <JobTrackingUrlField
        jobId={jobId}
        sourceUrl={jobSourceUrl ?? null}
        id="details-tracking-url"
        readOnly={readOnly}
      />

      <div className="grid gap-1.5">
        <Label htmlFor={referralId} className="text-label-medium">
          Referral
        </Label>
        <Select
          disabled={readOnly}
          value={app.referral_id ?? "__none__"}
          onValueChange={(v) =>
            onPatch({ referral_id: v === "__none__" ? null : v })
          }
        >
          <SelectTrigger id={referralId} size="sm" className="w-full">
            <SelectValue placeholder="None">
              {(() => {
                if (!app.referral_id) return "None";
                const selected = referrals?.find(
                  (r) => r.id === app.referral_id,
                );
                return selected ? referralLabel(selected) : "None";
              })()}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">None</SelectItem>
            {(referrals ?? []).map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {referralLabel(r)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor={notesId} className="text-label-medium">
          Notes
        </Label>
        <Textarea
          id={notesId}
          className="text-body-medium"
          value={notes}
          disabled={!canRequest}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            if (notes !== (app.notes ?? "")) onPatch({ notes });
          }}
          rows={3}
        />
      </div>

      <div>
        <Button
          variant="destructive"
          size="sm"
          onClick={onDelete}
          disabled={deleting || readOnly}
        >
          {deleting ? <Loader2 className="animate-spin" /> : <Trash2 />}
          {deleting ? "Deleting…" : "Delete application"}
        </Button>
      </div>
    </div>
  );
}
