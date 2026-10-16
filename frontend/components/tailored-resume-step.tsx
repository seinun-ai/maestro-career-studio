"use client";

import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ChevronDown,
  FileOutput,
  Pencil,
  Trash2,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { toast } from "sonner";

import { useConfirmDeleteApplication } from "@/components/application-panel";
import { AtsComparePanel, tailoredRescoreKey } from "@/components/ats-compare-panel";
import { GuardedLink as Link } from "@/components/guarded-link";
import { IconButton } from "@/components/icon-button";
import { PdfFileLine } from "@/components/pdf-file-line";
import { ResumesFolderNote } from "@/components/resumes-folder-actions";
import { ProvenanceChip, revertHunk, sideText } from "@/components/resume-editor/diff-review";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useSingleFlight } from "@/hooks/use-single-flight";
import {
  ApiError,
  apiFetch,
  resumeDiffQuery,
  runAtsScoreTarget,
} from "@/lib/api";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { focusIfDropped, focusSuccessorIn } from "@/lib/focus";
import type { StepKey } from "@/lib/job-steps";
import { notifyRenderNote } from "@/lib/render-note";
import { hunkIds, hunkPlace } from "@/lib/resume-diff";
import { resumeDataSchema } from "@/lib/resume-schema";
import { RESUMES_FOLDER_KEY } from "@/lib/resumes-folder";
import { pdfActionWords } from "@/lib/studio";
import type { Application, RenderResult, ResumeData, ResumeDiff, ResumeDiffHunk } from "@/lib/types";
import { cn } from "@/lib/utils";

const MoreIcon = CONCEPT_ICONS.more;
const TailorIcon = CONCEPT_ICONS.tailor;

/** The header's tally for one provenance: its chip, then the count as its own badge ("3", read "3 changes"). */
function ProvenanceCount({ value, count }: { value: ResumeDiffHunk["provenance"]; count: number }) {
  if (value === "llm" || count === 0) return null;
  return (
    <span className="inline-flex items-center gap-1">
      <ProvenanceChip value={value} tinted />
      <span className="bg-surface-container inline-flex h-5 items-center rounded-full px-1.5 text-label-small tabular-nums">
        <span aria-hidden="true">{count}</span>
        <span className="sr-only">{count === 1 ? "1 change" : `${count} changes`}</span>
      </span>
    </span>
  );
}

const SHOWN_CHANGES = 5;

/** A draft change written from step 3: a revert. `expectedUpdatedAt` is the draft the revert was computed from:
 *  the server refuses it (409, nothing written) if the row has moved since. Wording checks live in the studio
 *  (Edit resume), not here. */
type DraftWrite = {
  data: ResumeData;
  id: string;
  pdfRemoved: boolean;
  expectedUpdatedAt: string;
};

/**
 * Step 3's draft writes: one PATCH of `customized_json` at a time (each writes the whole draft, so two would
 * race), then the tailored score again. The server removes the PDF with the write; nothing creates it again
 * behind your back: the PDF card goes, Create PDF is the filled button again, and the toast says so. Focus moves
 * to a neighbouring row once the list without the reverted one is in, and a polite live region says what happened.
 */
function useDraftWrites({
  app,
  jobId,
  diffData,
}: {
  app: Application;
  jobId: string;
  /** The list on screen once it is the real one for the current draft (undefined while a previous one stands in). */
  diffData: ResumeDiff | undefined;
}) {
  const qc = useQueryClient();
  const [announced, setAnnounced] = useState({ text: "", n: 0 });
  const rescore = useMutation({
    // Shared with the full compare panel's Update score: one pending state for both.
    mutationKey: tailoredRescoreKey(app.id),
    mutationFn: () => runAtsScoreTarget(jobId, "application", app.id, "tailored"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ats-compare", app.id] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
    },
    onError: (err: Error) => toast.error(couldnt("update the match score", err)),
  });
  const focusAfterWrite = useRef<(() => HTMLElement | null) | null>(null);
  const writeDraft = useMutation({
    mutationFn: (write: DraftWrite) =>
      apiFetch<Application>(`/api/applications/${app.id}`, {
        method: "PATCH",
        body: JSON.stringify({ customized_json: write.data, expected_updated_at: write.expectedUpdatedAt }),
      }),
    onSuccess: (_result, write) => {
      rescore.mutate();
      setAnnounced((prev) => ({ text: "Change reverted", n: prev.n + 1 }));
      if (write.pdfRemoved) toast.success("Change reverted. Create the PDF again when you are done.");
    },
    onError: (err: Error) => {
      focusAfterWrite.current = null;
      toast.error(couldnt("revert the change", err));
    },
    // Returned, so the row stays pending until the list without it is in. A 409 (the row moved) refreshes both too.
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["resume-diff", app.id] }),
        qc.invalidateQueries({ queryKey: ["job-detail", jobId] }),
        qc.invalidateQueries({ queryKey: ["application", app.id] }),
      ]),
  });
  const writeOnce = useSingleFlight(writeDraft.mutate);
  // A reverted row leaves the list: focus goes to its neighbour, or to the list, never to <body>.
  // Only on the real list: the previous one standing in still holds the reverted row.
  useLayoutEffect(() => {
    const next = focusAfterWrite.current;
    if (!next || !diffData) return;
    focusAfterWrite.current = null;
    focusIfDropped(next());
  }, [diffData]);
  return {
    write: (write: DraftWrite, focusNext?: () => HTMLElement | null) => {
      focusAfterWrite.current = focusNext ?? null;
      writeOnce(write);
    },
    writing: writeDraft.isPending ? writeDraft.variables : null,
    pending: writeDraft.isPending,
    // A trailing no-break space on every other message, so the same words twice are announced twice.
    announcement: announced.text + (announced.n % 2 ? " " : ""),
  };
}

/**
 * Step 3, Tailored resume, inside one card: the score strip, the full compare behind Score breakdown, the changes
 * tailoring made with a Revert on each, and once a PDF exists the PDF card. A revert is computed
 * from the draft the diff describes (the diff's `updated_at` is the application's) and sent with it, so the server
 * refuses one the row has moved past.
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

  // A new draft is a new key: the previous list stands in while the new one loads (no "No changes" flash), and
  // nothing in it can be reverted until the real one is in.
  const diff = useQuery({ ...resumeDiffQuery(app, hasDraft), placeholderData: keepPreviousData });
  const diffSettled = !diff.isPlaceholderData && !diff.isFetching;
  const hunks = diff.data?.hunks ?? [];
  const ids = hunkIds(hunks);
  const writes = useDraftWrites({ app, jobId, diffData: diff.isPlaceholderData ? undefined : diff.data });

  /** The draft as the editor reads it; null when it does not parse (the toast names that, not a moved text). */
  const parsedDraft = (): ResumeData | null => {
    const parsed = resumeDataSchema.safeParse(app.customized_json);
    return parsed.success ? parsed.data : null;
  };
  const unreadable = () =>
    toast.error("Couldn't read this tailored resume, so nothing changed. Open Edit resume to fix it.");
  const onRevert = (hunk: ResumeDiffHunk, id: string, button: HTMLElement) => {
    // The diff must describe the draft the revert edits: the server says which one it diffed.
    if (diff.data?.updated_at !== app.updated_at) {
      toast.error("The changes were out of date and have been refreshed. Try again.");
      void qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      void diff.refetch();
      return;
    }
    const current = parsedDraft();
    if (!current) return unreadable();
    const next = revertHunk(current, hunk);
    if (!next) {
      toast.error("Couldn't revert this change because the text has changed since. Edit it yourself.");
      return;
    }
    writes.write(
      { data: next, id, pdfRemoved: hasPdf, expectedUpdatedAt: app.updated_at },
      focusSuccessorIn(button, "[data-revert]"),
    );
  };

  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const breakdownId = useId();
  // The PDF and the draft write the same row: neither starts while the other runs.
  const busy = renderPdf.isPending || writes.pending;

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

  // The view's one filled button: Create PDF before a PDF, Continue to Apply once one exists.
  const filled = hasPdf ? (
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
  );
  const updatePdf = (
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
  );

  return (
    <Card>
      <CardContent className="space-y-4">
        <ScoreStrip
          app={app}
          jobId={jobId}
          readOnly={readOnly}
          onOpenStep={onOpenStep}
          breakdown={
            <Button
              variant="link"
              size="sm"
              className="h-auto px-1"
              aria-expanded={breakdownOpen}
              aria-controls={breakdownId}
              onClick={() => setBreakdownOpen(!breakdownOpen)}
            >
              Score breakdown
              <ChevronDown
                aria-hidden="true"
                className={cn("size-3.5 transition-[rotate] duration-short3 ease-standard", breakdownOpen && "rotate-180")}
              />
            </Button>
          }
          filled={filled}
        />
        {/* The full compare (subscore bars, each skill Gained, Lost or Same, Update score), under the strip. */}
        <div id={breakdownId} hidden={!breakdownOpen} className="rounded-corner-md border p-4">
          {breakdownOpen ? <AtsComparePanel app={app} jobId={jobId} readOnly={readOnly} bare /> : null}
        </div>

        {/* A Create PDF that failed, with no PDF to keep showing: say so where the PDF would be. */}
        {!hasPdf && app.render_error && !renderPdf.isPending ? (
          <p className="bg-error-container text-on-error-container flex items-start gap-2 rounded-corner-md px-3 py-2 text-body-small">
            <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            Creating the PDF failed. Try again.
          </p>
        ) : null}

        <ChangesList
          diff={diff}
          hunks={hunks}
          ids={ids}
          draft={app.customized_json}
          hasPdf={hasPdf}
          disabled={busy || readOnly || !diffSettled}
          writing={writes.writing}
          announcement={writes.announcement}
          onRevert={onRevert}
        />

        {hasPdf ? (
          <PdfCard
            app={app}
            copyMissed={renderPdf.data?.copy_path === null}
            update={updatePdf}
            preview={
              <div className="h-[80vh] min-h-[520px] overflow-hidden rounded-corner-md border"
                data-pending={renderPdf.isPending ? "true" : undefined}
              >
                <PdfPagesPreview
                  basePath={`/api/applications/${app.id}`}
                  version={`${app.updated_at}-${previewVersion}`}
                  emptyMessage="Couldn't show the preview. Update the PDF to try again."
                />
              </div>
            }
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

/** The strip: the compact compare and Score breakdown, then ⋯, Edit resume and the view's filled button, last. */
function ScoreStrip({
  app,
  jobId,
  readOnly,
  onOpenStep,
  breakdown,
  filled,
}: {
  app: Application;
  jobId: string;
  readOnly: boolean;
  onOpenStep: (key: StepKey) => void;
  breakdown: ReactNode;
  filled: ReactNode;
}) {
  return (
    <div className="bg-surface-container-low flex flex-wrap items-center gap-2 rounded-corner-md py-2 pr-2 pl-4">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
        <AtsComparePanel app={app} jobId={jobId} readOnly={readOnly} compact />
        {breakdown}
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
      {filled}
    </div>
  );
}

/**
 * Changes (N): the header with its provenance tallies, then what the list could not show (loading, "No changes
 * yet" for a 409, a load error) and the rows (the only part that folds once a PDF exists).
 */
function ChangesList({
  diff,
  hunks,
  ids,
  draft,
  hasPdf,
  disabled,
  writing,
  announcement,
  onRevert,
}: {
  diff: { isLoading: boolean; isError: boolean; error: Error | null; data: ResumeDiff | undefined; refetch: () => unknown };
  hunks: ResumeDiffHunk[];
  ids: string[];
  draft: Record<string, unknown> | null;
  hasPdf: boolean;
  disabled: boolean;
  writing: DraftWrite | null | undefined;
  announcement: string;
  onRevert: (hunk: ResumeDiffHunk, id: string, button: HTMLElement) => void;
}) {
  const listId = useId();
  const [listShown, setListShown] = useState<boolean | null>(null);
  const [allShown, setAllShown] = useState(false);
  // Before a PDF the changes are the body; once one exists the rows fold under the header.
  const listOpen = listShown ?? !hasPdf;
  const nothingTailored = diff.error instanceof ApiError && diff.error.status === 409;
  const shown = allShown ? hunks : hunks.slice(0, SHOWN_CHANGES);
  const count = (p: ResumeDiffHunk["provenance"]) => hunks.filter((h) => h.provenance === p).length;

  return (
    <section aria-labelledby={`${listId}-title`} tabIndex={-1} className="space-y-2 outline-none">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`${listId}-title`} className="text-title-small">
          {diff.data ? `Changes (${hunks.length})` : "Changes"}
        </h2>
        <ProvenanceCount value="kb_auto" count={count("kb_auto")} />
        <ProvenanceCount value="user" count={count("user")} />
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
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      {/* Outside the fold: what the list could not show. Only the rows fold. */}
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
        <div id={listId} hidden={!listOpen} className="space-y-2">
          <ul className="divide-y">
            {shown.map((hunk, position) => {
              const id = ids[position];
              const placeId = `${listId}-place-${position}`;
              const before = sideText(hunk.before);
              const after = sideText(hunk.after);
              return (
                <li key={id} className="flex items-start gap-3 py-2">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span id={placeId} className="text-muted-foreground text-body-small">
                        {hunkPlace(hunk, draft)}
                      </span>
                      <ProvenanceChip value={hunk.provenance} tinted />
                    </div>
                    {before ? (
                      <p className="text-muted-foreground text-body-small">
                        <del>
                          <span className="sr-only">Before: </span>
                          {before}
                        </del>
                      </p>
                    ) : null}
                    {after ? (
                      <p className="text-body-medium">
                        <ins className="no-underline">
                          <span className="sr-only">Now: </span>
                          {after}
                        </ins>
                      </p>
                    ) : null}
                  </div>
                  <IconButton
                    data-revert=""
                    label="Revert this change"
                    aria-describedby={placeId}
                    icon={<Undo2 className="size-4" />}
                    pending={writing?.id === id}
                    disabled={disabled}
                    focusableWhenDisabled
                    className="shrink-0 data-disabled:pointer-events-none data-disabled:opacity-50"
                    onClick={(e) => onRevert(hunk, id, e.currentTarget)}
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
        </div>
      )}
    </section>
  );
}

/**
 * The PDF card, only while a PDF exists: its line (the file, its pages, where its copy is, and its own actions),
 * then the page preview. `canvas` is only the ground the preview paints behind the page.
 */
function PdfCard({
  app,
  copyMissed,
  update,
  preview,
}: {
  app: Application;
  copyMissed: boolean;
  update: ReactNode;
  preview: ReactNode;
}) {
  return (
    <section aria-label="PDF" className="space-y-3">
      <PdfFileLine app={app} note={<ResumesFolderNote copyMissed={copyMissed} />} actions={update} />
      {preview}
    </section>
  );
}

/** The strip's ⋯: Tailor again (step 2) and Delete application, with Application details' confirm. */
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
