"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { queryOptions, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Download,
  ExternalLink,
  FileOutput,
  FileText,
  Loader2,
  Pencil,
  SlidersHorizontal,
  SpellCheck,
  Trash2,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { toast } from "sonner";
import { isSyncQueued } from "@/lib/job-ownership";

import { AtsComparePanel } from "@/components/ats-compare-panel";
import { useConfirm } from "@/components/confirm-dialog";
import { GuardedLink as Link } from "@/components/guarded-link";
import { IconButton } from "@/components/icon-button";
import { ResumesFolderNote, ShowCopyButton } from "@/components/resumes-folder-actions";
import {
  type ApplicableCoherenceProposal,
  applyCoherenceProposal,
  CoherenceResults,
  type CoherenceState,
  hunkKey,
  KIND_LABELS,
  revertHunk,
  SECTION_LABELS,
  sideText,
} from "@/components/resume-editor/diff-review";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { JobTrackingUrlField } from "@/components/job-tracking-url-field";
import { ActorChip, ResumeTag } from "@/components/visual";
import { useBaseResumeColor, useBaseResumeName } from "@/hooks/use-base-resume-label";
import { useSingleFlight } from "@/hooks/use-single-flight";
import {
  ApiError,
  apiFetch,
  apiUrlForBrowserPdf,
  getResumeDiff,
  runAtsScoreTarget,
  runCoherenceCheck,
} from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { focusIfDropped, focusSuccessorIn } from "@/lib/focus";
import type { StepKey } from "@/lib/job-steps";
import { notifyRenderNote } from "@/lib/render-note";
import { resumeDataSchema } from "@/lib/resume-schema";
import { RESUMES_FOLDER_KEY } from "@/lib/resumes-folder";
import { pdfActionWords } from "@/lib/studio";
import type { Application, JobDetail, Referral, RenderResult, ResumeData, ResumeDiffHunk } from "@/lib/types";

const MoreIcon = CONCEPT_ICONS.more;
const TailorIcon = CONCEPT_ICONS.tailor;

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

/** Delete application with its confirm, for the Details menu and step 3's ⋯ (one sentence, one request). */
function useConfirmDeleteApplication({
  applicationId,
  jobId,
  returnFocus,
}: {
  applicationId: string;
  jobId: string;
  returnFocus?: () => HTMLElement | null;
}) {
  const confirm = useConfirm();
  const { deleteApp } = useApplicationMutations({ applicationId, jobId });
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
 * The application's tracking details behind one quiet menu button: applied
 * date, tracking URL, base, referral, notes, delete. Status is NOT here — it
 * lives in the always-visible StatusChip beside this menu (one click, no
 * drill-down).
 */
export function ApplicationDetailsMenu({
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
  const [open, setOpen] = useState(false);
  // Job detail embeds ApplicationRead, which carries no joined name. The hook
  // names it from the list, and reads the résumé's own row only when the list
  // lacks it (soft-deleted) and the menu is open.
  const listedName = useBaseResumeName(app.base_resume, open && !app.base_resume_name);
  const resumeName = app.base_resume_name || listedName;
  const colorOf = useBaseResumeColor();
  const { patch } = useApplicationMutations({
    applicationId: app.id,
    jobId,
  });
  const { onDelete, deleting } = useConfirmDeleteApplication({ applicationId: app.id, jobId });
  // Referrals are only visible inside the opened menu — don't fetch them on
  // every job-detail view (review finding).
  const { data: referrals } = useQuery({
    queryKey: ["referrals"],
    queryFn: () => apiFetch<Referral[]>("/api/referrals"),
    enabled: open,
  });

  const onPatch = (body: Partial<Application>) => {
    if (readOnly && (!canRequest || Object.keys(body).some((key) => key !== "notes"))) return;
    patch.mutate(body);
  };

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
              disabled={readOnly}
              onChange={(e) => setAppliedAt(e.target.value)}
              onBlur={() => onPatch({ applied_at: toIsoDate(appliedAt) })}
            />
          </div>

          <JobTrackingUrlField
            jobId={jobId}
            sourceUrl={jobSourceUrl ?? null}
            id="menu-tracking-url"
            readOnly={readOnly}
          />

          <div className="grid gap-1">
            <span className="text-muted-foreground text-body-small">Base resume</span>
            <ResumeTag hue={colorOf(app.base_resume)} className="text-body-medium">{resumeName}</ResumeTag>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="menu-referral" className="text-label-medium">
              Referral
            </Label>
            <Select
              disabled={readOnly}
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
              disabled={!canRequest}
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
            disabled={deleting || readOnly}
          >
            {deleting ? <Loader2 className="animate-spin" /> : <Trash2 />}
            {deleting ? "Deleting…" : "Delete application"}
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The base-to-tailored diff (`GET …/resume-diff`), one key for step 3's list, the page's step line and the studio. */
export function resumeDiffQuery(applicationId: string, enabled = true) {
  return queryOptions({
    queryKey: ["resume-diff", applicationId],
    queryFn: () => getResumeDiff(applicationId),
    // A 409 is "nothing tailored yet": an answer, not a failure to retry.
    retry: false,
    staleTime: 30_000,
    enabled,
  });
}

/** Each provenance's word and its container pair. `llm` has none: it is the server's word for a change it could not
 *  attribute (an edit in the studio reads as one too), so calling it an AI rewrite would claim what nobody knows. */
const PROVENANCE: Record<
  Exclude<ResumeDiffHunk["provenance"], "llm">,
  { kind: "careerHistory" | "you"; name: string; title: string; tone: string }
> = {
  kb_auto: {
    kind: "careerHistory",
    name: "From career history",
    title: "Taken from your career history",
    tone: "bg-success-container text-on-success-container",
  },
  user: {
    kind: "you",
    name: "Yours",
    title: "From an answer you gave",
    tone: "bg-primary-container text-on-primary-container",
  },
};

function ProvenanceTag({ value, count }: { value: ResumeDiffHunk["provenance"]; count?: number }) {
  if (value === "llm") return null;
  const { kind, name, title, tone } = PROVENANCE[value];
  return <ActorChip kind={kind} name={count == null ? name : `${name} · ${count}`} title={title} className={tone} />;
}

/** Where a change sits: its section, the item it belongs to (a bullet's job or project) and what happened. */
function hunkPlace(hunk: ResumeDiffHunk, draft: Record<string, unknown> | null): string {
  const list = draft?.[hunk.section];
  const owner =
    hunk.kind.startsWith("bullet_") && hunk.section !== "certifications" && hunk.index != null && Array.isArray(list)
      ? (list[hunk.index] as Record<string, unknown> | undefined)
      : undefined;
  const ownerName = owner
    ? [owner.company, owner.name, owner.institution, owner.title].find((v): v is string => typeof v === "string" && !!v)
    : undefined;
  return [SECTION_LABELS[hunk.section] ?? hunk.section, ownerName, KIND_LABELS[hunk.kind]].filter(Boolean).join(" · ");
}

const SHOWN_CHANGES = 5;

/** A draft change written from step 3: a revert, or a wording fix from Check wording. */
type DraftWrite = { data: ResumeData; key: string; kind: "revert" | "apply"; hadPdf: boolean };

/**
 * Step 3, Tailored resume, inside one card: a score strip (the compact before/after compare, ⋯, Edit resume and
 * the view's one filled button: Create PDF, then Continue to Apply), the changes tailoring made with a Revert on
 * each, Check wording, and once a PDF exists the PDF card with its own actions and the page preview. A draft
 * change removes the PDF on the server, so a PDF that exists is the draft's: there is no stale state to show.
 */
export function TailoredResumeStep({
  app,
  jobId,
  readOnly = false,
  onOpenStep,
}: {
  app: Application;
  jobId: string;
  readOnly?: boolean;
  onOpenStep: (key: StepKey) => void;
}) {
  const qc = useQueryClient();
  const [previewVersion, setPreviewVersion] = useState(0);
  const hasDraft = !!app.customized_json;
  const hasPdf = !!app.pdf_path;
  const pdfWords = pdfActionWords(hasPdf);
  const renderPdf = useMutation({
    mutationFn: () =>
      apiFetch<RenderResult>(`/api/applications/${app.id}/render`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      setPreviewVersion((version) => version + 1);
      qc.invalidateQueries({ queryKey: ["application", app.id] });
      qc.invalidateQueries({
        queryKey: ["pdf-preview", `/api/applications/${app.id}`],
      });
      qc.invalidateQueries({ queryKey: RESUMES_FOLDER_KEY }); // a failed copy records an error the note must see
      notifyRenderNote(result);
      toast.success("PDF ready");
      // Returned, so the button stays pending until the job's PDF is in: Create PDF never flashes back.
      return qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
    },
    onError: (error: Error) => {
      // The failure is saved on the application (render_error): the refetch shows it.
      void qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      toast.error(couldnt(pdfWords.failure, error));
    },
  });
  // A double click rendered twice and toasted twice.
  const renderOnce = useSingleFlight(renderPdf.mutate);

  const diff = useQuery(resumeDiffQuery(app.id, hasDraft));
  const hunks = diff.data?.hunks ?? [];
  const nothingTailored = diff.error instanceof ApiError && diff.error.status === 409;
  const draft = app.customized_json;

  // The tailored score reads the draft, so a write scores it again (the studio's Save does the same).
  const rescore = useMutation({
    mutationFn: () => runAtsScoreTarget(jobId, "application", app.id, "tailored"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ats-compare", app.id] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
    },
    onError: (err: Error) => toast.error(couldnt("update the match score", err)),
  });

  const [coherence, setCoherence] = useState<CoherenceState>({
    checked: false,
    loading: false,
    flags: [],
    appliedKeys: new Set(),
  });
  const checkWording = useMutation({
    mutationFn: () => runCoherenceCheck(app.id),
    onSuccess: (result) =>
      setCoherence({
        checked: true,
        loading: false,
        flags: result.flags,
        hygiene: result.hygiene,
        gates: result.gates,
        appliedKeys: new Set(),
      }),
    onError: () => toast.error("Couldn't run the checks. Try again."),
  });
  const checkOnce = useSingleFlight(checkWording.mutate);

  // A revert or a fix writes the whole draft, so one runs at a time: one guard for every row.
  const focusAfterWrite = useRef<(() => HTMLElement | null) | null>(null);
  const writeDraft = useMutation({
    mutationFn: (write: DraftWrite) =>
      apiFetch<Application>(`/api/applications/${app.id}`, {
        method: "PATCH",
        body: JSON.stringify({ customized_json: write.data }),
      }),
    onSuccess: (_result, write) => {
      if (write.kind === "apply") {
        setCoherence((prev) => ({ ...prev, appliedKeys: new Set(prev.appliedKeys).add(write.key) }));
      }
      rescore.mutate();
      // The write removed the PDF: make it again, as the studio's Save does, so the PDF card stays.
      if (write.hadPdf) renderOnce();
    },
    onError: (err: Error, write) => {
      focusAfterWrite.current = null;
      toast.error(couldnt(write.kind === "revert" ? "revert the change" : "apply the fix", err));
    },
    // Returned, so the row stays pending until the list without it is in.
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["resume-diff", app.id] }),
        qc.invalidateQueries({ queryKey: ["job-detail", jobId] }),
        qc.invalidateQueries({ queryKey: ["application", app.id] }),
      ]),
  });
  const writeOnce = useSingleFlight(writeDraft.mutate);
  const writing = writeDraft.isPending ? writeDraft.variables : null;
  // A reverted row leaves the list: focus goes to its neighbour, or to the list, never to <body>.
  useLayoutEffect(() => {
    const next = focusAfterWrite.current;
    if (!next) return;
    focusAfterWrite.current = null;
    focusIfDropped(next());
  }, [diff.data]);

  const parsedDraft = (): ResumeData | null => {
    const parsed = resumeDataSchema.safeParse(app.customized_json);
    return parsed.success ? parsed.data : null;
  };
  const onRevert = (hunk: ResumeDiffHunk, key: string, button: HTMLElement) => {
    const current = parsedDraft();
    const next = current && revertHunk(current, hunk);
    if (!next) {
      toast.error("Couldn't revert this change because the text has changed since. Edit it yourself.");
      return;
    }
    focusAfterWrite.current = focusSuccessorIn(button, "[data-revert]");
    writeOnce({ data: next, key, kind: "revert", hadPdf: hasPdf });
  };
  const onApplyFix = (flag: ApplicableCoherenceProposal, key: string) => {
    const current = parsedDraft();
    const next = current && applyCoherenceProposal(current, flag);
    if (!next) {
      toast.error("Couldn't find that text. It may have changed. Make the fix yourself.");
      return;
    }
    writeOnce({ data: next, key, kind: "apply", hadPdf: hasPdf });
  };

  const [listShown, setListShown] = useState<boolean | null>(null);
  const [allShown, setAllShown] = useState(false);
  // Before a PDF the changes are the body; once one exists the list folds to its header.
  const listOpen = listShown ?? !hasPdf;
  const listId = useId();
  const shown = allShown ? hunks : hunks.slice(0, SHOWN_CHANGES);
  const counts = hunks.reduce<Partial<Record<ResumeDiffHunk["provenance"], number>>>(
    (acc, h) => ({ ...acc, [h.provenance]: (acc[h.provenance] ?? 0) + 1 }),
    {},
  );

  // The PDF and the draft write the same row: neither starts while the other runs.
  const busy = renderPdf.isPending || writeDraft.isPending;
  const pdfHref = apiUrlForBrowserPdf(`/api/applications/${app.id}/pdf`);
  const pdfFilename = app.pdf_path?.split(/[\\/]/).pop() ?? "tailored-resume.pdf";
  const pdfFacts = app.pdf_pages ? `${app.pdf_pages} ${app.pdf_pages === 1 ? "page" : "pages"}` : null;

  if (!hasDraft) {
    // An application with no resume of its own (marked applied without tailoring).
    return (
      <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-corner-md border border-dashed p-8 text-center text-body-medium">
        <p>No tailored resume yet.</p>
        <Button size="sm" variant="link" onClick={() => onOpenStep("fit")}>
          Go to Resume and gaps
        </Button>
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-4">
        {/* The score strip: the compare, then the step's actions; the filled one is last. */}
        <div className="bg-surface-container-low flex flex-wrap items-center gap-2 rounded-corner-md py-2 pr-2 pl-4">
          <div className="min-w-0 flex-1">
            <AtsComparePanel app={app} jobId={jobId} readOnly={readOnly} compact />
          </div>
          <TailoredResumeMenu app={app} jobId={jobId} readOnly={readOnly} onOpenStep={onOpenStep} />
          <Button
            variant="outline"
            disabled={readOnly}
            aria-disabled={readOnly || undefined}
            // A link rendered as a button: `disabled:` never matches it, `data-disabled` does.
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            nativeButton={false}
            render={
              <Link href={`/applications/${app.id}/resume`}>
                <Pencil className="size-4" />
                Edit resume
              </Link>
            }
          />
          {hasPdf ? (
            <Button onClick={() => onOpenStep("qa")}>
              Continue to Apply
              <ArrowRight data-icon="inline-end" className="size-4" />
            </Button>
          ) : (
            <Button
              onClick={() => renderOnce()}
              // Focusable while it creates: a natively disabled button dropped focus to <body>.
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              focusableWhenDisabled
              pending={renderPdf.isPending}
              disabled={busy || readOnly}
            >
              <FileOutput className="size-4" />
              {renderPdf.isPending ? pdfWords.pending : pdfWords.label}
            </Button>
          )}
        </div>

        {/* A Create PDF that failed, with no PDF to keep showing: say so where the PDF would be. */}
        {!hasPdf && app.render_error && !renderPdf.isPending ? (
          <p className="bg-error-container text-on-error-container flex items-start gap-2 rounded-corner-md px-3 py-2 text-body-small">
            <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            The last Create PDF failed. Check your last change, then create the PDF again.
          </p>
        ) : null}

        <section aria-labelledby={`${listId}-title`} tabIndex={-1} className="space-y-2 outline-none">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={`${listId}-title`} className="text-title-small">
              {diff.data ? `Changes (${hunks.length})` : "Changes"}
            </h2>
            {(["kb_auto", "user"] as const).map((p) =>
              counts[p] ? <ProvenanceTag key={p} value={p} count={counts[p]} /> : null,
            )}
            {hasPdf && hunks.length > 0 ? (
              <Button
                variant="link"
                size="sm"
                className="ml-auto"
                aria-expanded={listOpen}
                aria-controls={listId}
                onClick={() => setListShown(!listOpen)}
              >
                {listOpen ? "Hide" : "Show"}
              </Button>
            ) : null}
          </div>
          <div id={listId} hidden={!listOpen} className="space-y-2">
            {diff.isLoading ? (
              <Skeleton className="animate-shimmer h-16 w-full" />
            ) : nothingTailored ? (
              <p className="text-muted-foreground text-body-medium">No changes yet.</p>
            ) : diff.isError ? (
              <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-body-medium">
                {couldnt("load the changes", diff.error)}
                <Button variant="link" size="sm" onClick={() => void diff.refetch()}>
                  Try again
                </Button>
              </div>
            ) : hunks.length === 0 ? (
              <p className="text-muted-foreground text-body-medium">No changes from your base resume.</p>
            ) : (
              <>
                <ul className="divide-y">
                  {shown.map((hunk, position) => {
                    const key = hunkKey(hunk, position);
                    const before = sideText(hunk.before);
                    const after = sideText(hunk.after);
                    return (
                      <li key={key} className="flex items-start gap-3 py-2">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <ProvenanceTag value={hunk.provenance} />
                            <span className="text-muted-foreground text-body-small">{hunkPlace(hunk, draft)}</span>
                          </div>
                          {before ? (
                            <p className="text-muted-foreground text-body-small line-through">{before}</p>
                          ) : null}
                          {after ? <p className="text-body-medium">{after}</p> : null}
                        </div>
                        <IconButton
                          data-revert=""
                          label="Revert this change"
                          icon={<Undo2 className="size-4" />}
                          pending={writing?.kind === "revert" && writing.key === key}
                          disabled={busy || readOnly}
                          focusableWhenDisabled
                          className="shrink-0 data-disabled:pointer-events-none data-disabled:opacity-50"
                          onClick={(e) => onRevert(hunk, key, e.currentTarget)}
                        />
                      </li>
                    );
                  })}
                </ul>
                {hunks.length > SHOWN_CHANGES ? (
                  <Button variant="link" size="sm" aria-expanded={allShown} onClick={() => setAllShown(!allShown)}>
                    {allShown ? "Show fewer changes" : `Show ${hunks.length - SHOWN_CHANGES} more changes`}
                  </Button>
                ) : null}
              </>
            )}
            {hunks.length > 0 ? (
              <div className="space-y-2">
                <Button
                  variant="ghost"
                  size="sm"
                  pending={checkWording.isPending}
                  onClick={() => checkOnce()}
                >
                  <SpellCheck className="size-3.5" />
                  {checkWording.isPending ? "Checking…" : coherence.checked ? "Check again" : "Check wording"}
                </Button>
                {coherence.checked && !checkWording.isPending ? (
                  <CoherenceResults
                    coherence={coherence}
                    onApply={readOnly ? undefined : (flag, key) => onApplyFix(flag, key)}
                    onApplyHygiene={
                      readOnly
                        ? undefined
                        : (flag, key) => {
                            if (flag.proposal !== null) onApplyFix({ ...flag, proposal: flag.proposal }, key);
                          }
                    }
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        {hasPdf ? (
          <div className="bg-canvas space-y-3 rounded-corner-md p-3">
            {/* The file's line: what it is, where its copy is, and what you can do with it. */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <FileText aria-hidden="true" className="text-muted-foreground size-4 shrink-0" />
              <span className="truncate text-title-small" title={pdfFilename}>
                {pdfFilename}
              </span>
              {pdfFacts ? <span className="text-muted-foreground text-body-small">· {pdfFacts}</span> : null}
              <ResumesFolderNote copyMissed={renderPdf.data?.copy_path === null} />
              <div className="ml-auto flex items-center gap-1">
                <IconButton
                  label="Download PDF"
                  icon={<Download className="size-4" />}
                  nativeButton={false}
                  render={<a href={pdfHref} download={pdfFilename} />}
                />
                <IconButton
                  label="Open PDF in new tab"
                  icon={<ExternalLink className="size-4" />}
                  nativeButton={false}
                  render={<a href={pdfHref} target="_blank" rel="noopener noreferrer" />}
                />
                <ShowCopyButton applicationId={app.id} variant="ghost" iconOnly />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => renderOnce()}
                  // Focusable while it updates: a natively disabled button dropped focus to <body>.
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  focusableWhenDisabled
                  pending={renderPdf.isPending}
                  disabled={busy || readOnly}
                >
                  <FileOutput className="size-3.5" />
                  {renderPdf.isPending ? pdfWords.pending : pdfWords.label}
                </Button>
              </div>
            </div>
            <div className="h-[80vh] min-h-[520px] overflow-hidden rounded-corner-md border"
              data-pending={renderPdf.isPending ? "true" : undefined}
            >
              <PdfPagesPreview
                basePath={`/api/applications/${app.id}`}
                version={`${app.updated_at}-${previewVersion}`}
                emptyMessage="Couldn't show the preview. Update the PDF to try again."
              />
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** The strip's ⋯: Tailor again (step 2) and Delete application, with the Details menu's confirm. */
function TailoredResumeMenu({
  app,
  jobId,
  readOnly,
  onOpenStep,
}: {
  app: Application;
  jobId: string;
  readOnly: boolean;
  onOpenStep: (key: StepKey) => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const { onDelete, deleting } = useConfirmDeleteApplication({
    applicationId: app.id,
    jobId,
    returnFocus: () => triggerRef.current,
  });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <IconButton
            ref={triggerRef}
            label="More actions for the tailored resume"
            icon={<MoreIcon className="size-4" />}
            className="text-muted-foreground shrink-0"
          />
        }
      />
      <DropdownMenuContent align="end" className="w-max">
        <DropdownMenuItem onClick={() => onOpenStep("fit")}>
          <TailorIcon />
          Tailor again
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" disabled={deleting || readOnly} onClick={onDelete}>
          <Trash2 />
          {deleting ? "Deleting…" : "Delete application"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
