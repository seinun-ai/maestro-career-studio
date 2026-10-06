"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  Download,
  ExternalLink,
  FileOutput,
  Loader2,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { AtsComparePanel } from "@/components/ats-compare-panel";
import { useConfirm } from "@/components/confirm-dialog";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useBaseResumeName } from "@/hooks/use-base-resume-label";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import type { Application, JobDetail, Referral, RenderResult } from "@/lib/types";

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
 * Used by ApplicationDetailsMenu, the header StatusChip, and any consumer
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
  const router = useRouter();

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

  return { patch, deleteApp };
}

/**
 * The application's tracking details behind one quiet menu button: applied
 * date, tracking URL, base, referral, notes, delete. Status is NOT here — it
 * lives in the always-visible StatusChip beside this menu (one click, no
 * drill-down).
 */
export function ApplicationDetailsMenu({
  app,
  jobId,
  jobSourceUrl,
}: {
  app: Application;
  jobId: string;
  jobSourceUrl?: string | null;
}) {
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  // Job detail embeds ApplicationRead, which carries no joined name. The hook
  // names it from the list, and reads the résumé's own row only when the list
  // lacks it (soft-deleted) and the menu is open.
  const listedName = useBaseResumeName(app.base_resume, open && !app.base_resume_name);
  const resumeName = app.base_resume_name || listedName;
  const { patch, deleteApp } = useApplicationMutations({
    applicationId: app.id,
    jobId,
  });
  // Referrals are only visible inside the opened menu — don't fetch them on
  // every job-detail view (review finding).
  const { data: referrals } = useQuery({
    queryKey: ["referrals"],
    queryFn: () => apiFetch<Referral[]>("/api/referrals"),
    enabled: open,
  });

  const onPatch = (body: Partial<Application>) => patch.mutate(body);
  const onDelete = async () => {
    const ok = await confirm({
      title: "Delete this application?",
      description:
        "This deletes its tailored resume, answers and PDF. The job stays saved.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!ok) return;
    deleteApp.mutate();
  };
  const deleting = deleteApp.isPending;

  const [appliedAt, setAppliedAt] = useState(formatDateInput(app.applied_at));
  const [notes, setNotes] = useState(app.notes ?? "");

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className="text-muted-foreground h-8 gap-1.5 px-3 text-body-small"
            aria-label="Application details"
          >
            <SlidersHorizontal className="size-3.5 opacity-60" />
            Details
          </Button>
        }
      />
      <DropdownMenuContent
        align="end"
        className="w-72 p-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-3">
          <p className="text-title-small">Application</p>

          <div className="grid gap-1.5">
            <Label htmlFor="menu-applied" className="text-label-medium">
              Applied on
            </Label>
            <Input
              id="menu-applied"
              type="date"
              className="h-8 text-body-medium"
              value={appliedAt}
              onChange={(e) => setAppliedAt(e.target.value)}
              onBlur={() => onPatch({ applied_at: toIsoDate(appliedAt) })}
            />
          </div>

          <JobTrackingUrlField
            jobId={jobId}
            sourceUrl={jobSourceUrl ?? null}
            id="menu-tracking-url"
          />

          <div className="grid gap-1">
            <span className="text-muted-foreground text-body-small">Base resume</span>
            <span className="text-body-medium">{resumeName}</span>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="menu-referral" className="text-label-medium">
              Referral
            </Label>
            <Select
              value={app.referral_id ?? "__none__"}
              onValueChange={(v) =>
                onPatch({ referral_id: v === "__none__" ? null : v })
              }
            >
              <SelectTrigger id="menu-referral" size="sm" className="w-full">
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
            <Label htmlFor="menu-notes" className="text-label-medium">
              Notes
            </Label>
            <Textarea
              id="menu-notes"
              className="text-body-medium"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => onPatch({ notes })}
              rows={3}
            />
          </div>

          <Button
            variant="destructive"
            size="sm"
            className="w-full"
            onClick={onDelete}
            disabled={deleting}
          >
            {deleting ? <Loader2 className="animate-spin" /> : <Trash2 />}
            {deleting ? "Deleting…" : "Delete application"}
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Draft, then PDF: each step a done or not-run icon with its word; the wrapper's label says both in one sentence. */
function ResumeSteps({ hasDraft, pdfReady }: { hasDraft: boolean; pdfReady: boolean }) {
  const step = (done: boolean, word: string) => {
    const Icon = done ? CONCEPT_ICONS.done : CONCEPT_ICONS.notRun;
    return (
      <span className="inline-flex items-center gap-1">
        <Icon aria-hidden="true" className={done ? "size-4 text-success" : "size-4 text-muted-foreground"} />
        {word}
      </span>
    );
  };
  return (
    <p
      role="img"
      aria-label={`Draft ${hasDraft ? "done" : "not started"}. PDF ${pdfReady ? "ready" : "not created yet"}`}
      className="text-muted-foreground flex items-center gap-1.5 text-body-medium"
    >
      {step(hasDraft, "Draft")}
      <ChevronRight aria-hidden="true" className="size-4" />
      {step(pdfReady, "PDF")}
    </p>
  );
}

export function OutputTab({ app, jobId }: { app: Application; jobId: string }) {
  const qc = useQueryClient();
  const [previewVersion, setPreviewVersion] = useState(0);
  const hasDraft = !!app.customized_json;
  const hasPdf = !!app.pdf_path;
  const renderPdf = useMutation({
    mutationFn: () =>
      apiFetch<RenderResult>(`/api/applications/${app.id}/render`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      setPreviewVersion((version) => version + 1);
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["application", app.id] });
      qc.invalidateQueries({
        queryKey: ["pdf-preview", `/api/applications/${app.id}`],
      });
      notifyRenderNote(result);
      toast.success("PDF ready");
    },
    onError: (error: Error) => toast.error(couldnt("create the PDF", error)),
  });
  // A double click rendered twice and toasted twice.
  const renderOnce = useSingleFlight(renderPdf.mutate);
  const pdfReady = hasPdf || renderPdf.isSuccess;
  const pdfHref = apiUrlForBrowserPdf(`/api/applications/${app.id}/pdf`);
  const pdfFilename =
    app.pdf_path?.split(/[\\/]/).pop() ?? "tailored-resume.pdf";

  return (
    <div className="space-y-4">
      {/* The ONE before/after compare surface, next to the artifact it
          describes (the ATS tab links here instead of double-mounting it). */}
      {hasDraft ? <AtsComparePanel app={app} jobId={jobId} /> : null}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
          <div className="space-y-1">
            {/* Not "Tailored": Use resume as is and Mark applied put the base resume here unchanged. */}
            <CardTitle>Resume for this job</CardTitle>
            <ResumeSteps hasDraft={hasDraft} pdfReady={pdfReady} />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => renderOnce()}
              // Focusable while it creates: a natively disabled button dropped focus to <body>.
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              focusableWhenDisabled
              disabled={!hasDraft || renderPdf.isPending}
            >
              {renderPdf.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <FileOutput className="size-4" />
              )}
              {renderPdf.isPending
                ? "Creating…"
                : pdfReady
                  ? "Update PDF"
                  : "Create PDF"}
            </Button>
            <Button
              variant="outline"
              nativeButton={false}
              disabled={!pdfReady}
              render={
                <a href={pdfHref} download={pdfFilename}>
                  <Download className="size-4" />
                  Download PDF
                </a>
              }
            />
            <Button
              variant="outline"
              nativeButton={false}
              disabled={!pdfReady}
              render={
                <a href={pdfHref} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4" />
                  Open in new tab
                </a>
              }
            />
          </div>
          {pdfReady ? (
            <div className="h-[80vh] min-h-[520px] overflow-hidden rounded-corner-md border"
              data-pending={renderPdf.isPending ? "true" : undefined}
            >
              <PdfPagesPreview
                basePath={`/api/applications/${app.id}`}
                version={`${app.updated_at}-${previewVersion}`}
                emptyMessage="Couldn't show the preview. Update the PDF to try again."
              />
            </div>
          ) : (
            <div className="text-muted-foreground flex h-40 items-center justify-center rounded-corner-md border border-dashed p-6 text-center text-body-medium">
              {hasDraft
                ? "No PDF yet."
                : "No tailored resume yet. Start on the Score and tailor tab."}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
