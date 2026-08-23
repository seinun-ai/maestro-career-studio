"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  GitCompare,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { IconButton } from "@/components/icon-button";
import { useUnsavedChangesWarning } from "@/hooks/use-unsaved-changes-warning";
import { PageHeader } from "@/components/page-shell";
import { ContactForm } from "@/components/resume-editor/contact-form";
import {
  type ApplicableCoherenceProposal,
  applyCoherenceProposal,
  type CoherenceState,
  DiffReviewPanel,
  revertHunk,
  sectionChangeCounts,
} from "@/components/resume-editor/diff-review";
import { EditorShell } from "@/components/resume-editor/editor-shell";
import { StudioOverflowMenu } from "@/components/resume-editor/studio-overflow";
import { StudioToolbar } from "@/components/resume-editor/studio-toolbar";
import { EducationEditor } from "@/components/resume-editor/education-editor";
import { ExperienceEditor } from "@/components/resume-editor/experience-editor";
import { ExtraSectionsEditor } from "@/components/resume-editor/extra-sections-editor";
import { FormattingPanel } from "@/components/resume-editor/formatting-panel";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { ProjectEditor } from "@/components/resume-editor/project-editor";
import { RawJsonToggle } from "@/components/resume-editor/raw-json-toggle";
import { SkillsEditor } from "@/components/resume-editor/skills-editor";
import { VersionHistorySheet } from "@/components/resume-versions/version-history-sheet";
import {
  DEFAULT_TEMPLATE,
  TemplateSelect,
  templateIdFromApi,
  templateIdToApi,
  useSupportedFmtKeys,
  useTemplateDefaults,
} from "@/components/templates/template-select";
import { Button } from "@/components/ui/button";
import { ChipListInput } from "@/components/ui/chip-input";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  apiFetch,
  apiUrlForBrowserPdf,
  getResumeDiff,
  runAtsScoreTarget,
  runCoherenceCheck,
} from "@/lib/api";
import { FORMATTING_DEFAULTS, type ResumeFormatting } from "@/lib/formatting";
import { resumeDataSchema } from "@/lib/resume-schema";
import type {
  Application,
  BaseResumeDetail,
  HygieneFlag,
  ResumeData,
  ResumeDiffHunk,
} from "@/lib/types";

const STUDIO_STORAGE_KEY = "tailoredResumeStudio";

/**
 * Structured "studio" for an application's tailored resume (`customized_json`).
 *
 * Reuses the pure base-resume section editors inside `EditorShell` (split
 * editor / live PDF preview), so the OutputTab and the dedicated
 * `/applications/[id]/resume` page share one editing surface. When the
 * application has no valid `customized_json` yet, it offers the materialize
 * affordance instead.
 *
 * The `application` prop only needs `Application` fields (`id`,
 * `customized_json`, `pdf_path`); `ApplicationDetail` extends `Application`, so
 * either shape can be passed.
 */
export function TailoredResumeStudio({
  application,
  jobId,
  jobLabel,
  backHref,
  reviewDefault = false,
}: {
  application: Application;
  jobId: string;
  /** Job title · company (or fallback) shown under the studio title. */
  jobLabel: string;
  /** Back target — usually the job output tab. */
  backHref: string;
  /**
   * Open in review mode (design §4.5). True when routed here straight from a
   * completed tailor (`?review=1`); the toggle stays available either way, and
   * review mode is an overlay — the plain editor is never fenced off.
   */
  reviewDefault?: boolean;
}) {
  const qc = useQueryClient();
  const applicationId = application.id;

  // Template lives here (not in StudioEditor) so a Save — which remounts the
  // customized_json-keyed StudioEditor — doesn't reset the chosen template.
  const [templateId, setTemplateId] = useState(
    templateIdFromApi(application.template_id),
  );

  // The render mutation and its cache-buster nonce live here (not in
  // StudioEditor) so a Save — which invalidates the application query and
  // remounts the customized_json-keyed StudioEditor — doesn't cancel an
  // in-flight render. This lets Save chain straight into render (auto-render
  // after save) without the remount tearing the render down.
  const [pdfNonce, setPdfNonce] = useState(0);

  // Lifted alongside `render` (below), for the same reason: Save invalidates
  // the application query and remounts the customized_json-keyed
  // StudioEditor, so the mutation driving the post-save auto re-score has to
  // live up here too or the remount would tear it down mid-chain. This is the
  // exact same mutation the manual "Re-score" button uses — reused, not
  // duplicated.
  const rescore = useMutation({
    mutationFn: () =>
      runAtsScoreTarget(jobId, "application", applicationId, "tailored"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ats-compare", applicationId] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      toast.success("Tailored resume re-scored");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const render = useMutation({
    mutationFn: (opts?: { thenRescore?: boolean }) =>
      apiFetch(
        `/api/applications/${applicationId}/render${
          templateId !== DEFAULT_TEMPLATE
            ? `?template_id=${encodeURIComponent(templateId)}`
            : ""
        }`,
        { method: "POST" },
      ),
    onSuccess: (_data, opts) => {
      toast.success("PDF rendered");
      setPdfNonce((n) => n + 1);
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["application", applicationId] });
      qc.invalidateQueries({ queryKey: ["pdf-preview"] });
      // Save chains straight into render (see StudioEditor's `save`), and a
      // stale-content save is exactly when the tailored ATS score has
      // drifted — chain the re-score so that doesn't happen silently.
      // A standalone re-render (the ⋯ recovery item) doesn't pass this, so a
      // retry of a FAILED render doesn't add a new "tailored" trajectory row
      // for content that hasn't changed.
      if (opts?.thenRescore) rescore.mutate();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const customizedKey =
    application.customized_json == null
      ? ""
      : JSON.stringify(application.customized_json);

  // Dirty-guard (SYSTEM.md §12): the editor is keyed on the ADOPTED server
  // snapshot, not the live `customizedKey`, so a foreign edit (chat/MCP) to the
  // same application no longer remounts StudioEditor and silently discards
  // in-progress studio edits. A newer server key is adopted (→ remount) only
  // when it's safe: right after our OWN Save, or when the editor is not dirty.
  // While dirty, a foreign change keeps the editor mounted and surfaces a banner.
  const [adoptedKey, setAdoptedKey] = useState(customizedKey);
  // Set true when our own Save lands so the resulting server key is adopted
  // WITHOUT the banner (Save→render→re-score chain must not break).
  const adoptNextServerKey = useRef(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const onDirtyChange = useCallback((dirty: boolean) => setEditorDirty(dirty), []);

  useEffect(() => {
    if (customizedKey === "" || customizedKey === adoptedKey) return;
    if (adoptNextServerKey.current || !editorDirty) {
      adoptNextServerKey.current = false;
      setAdoptedKey(customizedKey);
    }
    // else: a foreign change arrived while the user has unsaved edits — keep the
    // current editor mounted; `serverChanged` drives the inline reload banner.
  }, [customizedKey, adoptedKey, editorDirty]);

  const parseResumeData = (key: string): ResumeData | null => {
    if (key === "") return null;
    let raw: unknown;
    try {
      raw = JSON.parse(key) as unknown;
    } catch {
      return null;
    }
    const parsed = resumeDataSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  };
  // The editor initializes from the adopted snapshot, not the live one.
  const adoptedData = useMemo(() => parseResumeData(adoptedKey), [adoptedKey]);
  const serverChanged = customizedKey !== "" && customizedKey !== adoptedKey;

  const materialize = useMutation({
    mutationFn: () =>
      apiFetch<Application>(
        `/api/applications/${applicationId}/materialize-resume`,
        { method: "POST" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["application", applicationId] });
      toast.success("Draft built from the base resume");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  if (!adoptedData) {
    const parseFailed = application.customized_json != null;
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-6">
        <header className="flex min-w-0 flex-wrap items-center gap-3">
          <IconButton
            label="Back to application"
            icon={<ArrowLeft className="size-4" />}
            size="icon-sm"
            className="shrink-0"
            nativeButton={false}
            render={
              <Link href={backHref} className="text-muted-foreground" />
            }
          />
          <div>
            <h1 className="text-[22px] font-medium tracking-tight">
              Tailored resume
            </h1>
            <p className="text-muted-foreground text-sm">{jobLabel}</p>
          </div>
        </header>
        <div className="space-y-3 rounded-lg border p-6">
          {parseFailed ? (
            <p className="text-destructive text-sm">
              Stored resume data is invalid. Rebuild from the base resume to
              replace it.
            </p>
          ) : (
            <p className="text-muted-foreground text-sm">
              No tailored resume yet. Build a draft from your base resume, then
              refine it here and generate a PDF.
            </p>
          )}
          <Button
            onClick={() => materialize.mutate()}
            disabled={materialize.isPending}
          >
            {materialize.isPending
              ? "Building…"
              : "Build draft from base resume"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <StudioEditor
      key={adoptedKey}
      application={application}
      jobId={jobId}
      jobLabel={jobLabel}
      backHref={backHref}
      initialData={adoptedData}
      reviewDefault={reviewDefault}
      materializePending={materialize.isPending}
      onRebuild={() => materialize.mutate()}
      templateId={templateId}
      onTemplateChange={setTemplateId}
      render={render}
      rescore={rescore}
      pdfNonce={pdfNonce}
      serverChanged={serverChanged}
      onLoadLatest={() => setAdoptedKey(customizedKey)}
      onDirtyChange={onDirtyChange}
      onSaved={() => {
        adoptNextServerKey.current = true;
      }}
    />
  );
}

function StudioEditor({
  application,
  jobId,
  jobLabel,
  backHref,
  initialData,
  reviewDefault,
  materializePending,
  onRebuild,
  templateId,
  onTemplateChange,
  render,
  rescore,
  pdfNonce,
  serverChanged,
  onLoadLatest,
  onDirtyChange,
  onSaved,
}: {
  application: Application;
  jobId: string;
  jobLabel: string;
  backHref: string;
  initialData: ResumeData;
  reviewDefault: boolean;
  materializePending: boolean;
  onRebuild: () => void;
  templateId: string;
  onTemplateChange: (value: string) => void;
  // Lifted to TailoredResumeStudio so they survive the Save-triggered remount.
  render: {
    mutate: (opts?: { thenRescore?: boolean }) => void;
    isPending: boolean;
  };
  rescore: { mutate: () => void; isPending: boolean };
  pdfNonce: number;
  // Dirty-guard wiring (see TailoredResumeStudio): the parent adopts newer
  // server snapshots; this editor reports its dirty state up, flags its own
  // saves, and shows a reload banner when a foreign change arrives while dirty.
  serverChanged: boolean;
  onLoadLatest: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const applicationId = application.id;

  const [data, setData] = useState<ResumeData>(initialData);
  const [rawMode, setRawMode] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [formatting, setFormatting] = useState<Partial<ResumeFormatting> | null>(
    (application.formatting as Partial<ResumeFormatting> | null) ?? null,
  );
  const supportedFmtKeys = useSupportedFmtKeys(templateId);
  const templateDefaults = useTemplateDefaults(templateId);

  // The application inherits the base resume's formatting (backend merges
  // schema <- template default <- base <- application). Fetch the base so the
  // panel anchors on the *inherited* values and only stores genuine overrides of
  // them.
  const { data: baseResume } = useQuery({
    queryKey: ["base-resumes", application.base_resume],
    queryFn: () =>
      apiFetch<BaseResumeDetail>(
        `/api/base-resumes/${application.base_resume}`,
      ),
  });
  const formattingBaseline: ResumeFormatting = {
    ...FORMATTING_DEFAULTS,
    ...templateDefaults,
    ...((baseResume?.formatting as Partial<ResumeFormatting> | null) ?? {}),
  };


  // --- Review mode: the base→tailored diff, overlaid on the same editor -------
  // A 409 means "nothing tailored yet", i.e. there is nothing to review; any
  // other failure is equally uninteresting here, so BOTH just take the toggle
  // away rather than shouting at someone who came to edit a resume.
  const [review, setReview] = useState(reviewDefault);
  const [revertedKeys, setRevertedKeys] = useState<Set<string>>(new Set());
  const diff = useQuery({
    queryKey: ["resume-diff", applicationId],
    queryFn: () => getResumeDiff(applicationId),
    retry: false,
    staleTime: 30_000,
  });
  const reviewAvailable = !diff.isError;
  const hunks = useMemo(() => diff.data?.hunks ?? [], [diff.data]);
  const changeCounts = useMemo(() => sectionChangeCounts(hunks), [hunks]);
  const showReview = review && reviewAvailable;
  /** Count badge on a section tab, so review mode points at where to look. */
  const changeBadge = (tab: string) =>
    showReview && changeCounts[tab] ? (
      <span className="bg-primary/15 text-primary ml-1 rounded-full px-1.5 text-[10px] font-medium tabular-nums">
        {changeCounts[tab]}
      </span>
    ) : null;

  /**
   * Revert one hunk THROUGH THE STUDIO'S OWN EDIT PATH: the inverse lands in the
   * working copy, so it is saved (and version-snapshotted as `form_edit`) by the
   * same Save → render → re-score chain as any hand edit. No second write path,
   * no bespoke undo stack. A hunk that can no longer be located (already reverted
   * by hand, or reordered since the diff was computed) says so instead of
   * writing something arbitrary.
   */
  const handleRevert = (hunk: ResumeDiffHunk, key: string) => {
    const next = revertHunk(data, hunk);
    if (!next) {
      toast.error(
        "Couldn't revert this change automatically — it no longer matches the draft. Edit the section directly.",
      );
      return;
    }
    setData(next);
    setRevertedKeys((prev) => new Set(prev).add(key));
  };

  // --- Coherence lint (design §4.4): read-only flags, applied on click only ---
  const [coherence, setCoherence] = useState<CoherenceState>({
    checked: false,
    loading: false,
    flags: [],
    appliedKeys: new Set(),
  });
  const handleCheckCoherence = async () => {
    setCoherence((prev) => ({ ...prev, loading: true }));
    try {
      const result = await runCoherenceCheck(applicationId);
      setCoherence({
        checked: true,
        loading: false,
        flags: result.flags,
        hygiene: result.hygiene,
        gates: result.gates,
        appliedKeys: new Set(),
      });
    } catch {
      toast.error("Review checks failed — try again.");
      setCoherence((prev) => ({ ...prev, loading: false }));
    }
  };
  const handleApplyProposal = (
    flag: ApplicableCoherenceProposal,
    key: string,
  ) => {
    const next = applyCoherenceProposal(data, flag);
    if (!next) {
      toast.error(
        "Couldn't locate the flagged text — it may have been edited. Apply it manually.",
      );
      return;
    }
    setData(next);
    setCoherence((prev) => ({
      ...prev,
      appliedKeys: new Set(prev.appliedKeys).add(key),
    }));
  };
  // Hygiene notes reuse the proposal apply path, but only the mechanical ones
  // carry a proposal — the render guards the button on `proposal !== null`,
  // which TS can't narrow across the JSX closure, so re-check it here.
  const handleApplyHygiene = (flag: HygieneFlag, key: string) => {
    if (flag.proposal === null) return;
    handleApplyProposal({ ...flag, proposal: flag.proposal }, key);
  };

  // Dirty-state: the local working copy differs from the last-saved server
  // value. `initialData` is the parsed value `data` is initialized from and is
  // stable for this mount (StudioEditor is re-keyed on `customized_json`), so a
  // fresh mount starts clean and a successful Save — which remounts — clears it.
  const initialSerialized = useMemo(
    () => JSON.stringify(initialData),
    [initialData],
  );
  // Formatting can change independently of `customized_json`, so it feeds the
  // dirty flag too — otherwise a formatting-only edit couldn't be saved. The
  // baseline is the server value (`application.formatting`); an invalidated
  // application query after Save updates it, clearing the flag.
  const serverFormatting = JSON.stringify(application.formatting ?? null);
  // A template change alone is also a saveable edit — otherwise the choice could
  // be rendered with (via the render query param) but never persisted.
  const serverTemplateId = application.template_id ?? null;
  const dirty = useMemo(
    () =>
      JSON.stringify(data) !== initialSerialized ||
      JSON.stringify(formatting ?? null) !== serverFormatting ||
      templateIdToApi(templateId) !== serverTemplateId,
    [
      data,
      initialSerialized,
      formatting,
      serverFormatting,
      templateId,
      serverTemplateId,
    ],
  );

  useUnsavedChangesWarning(dirty);

  // Report dirty state up so the parent adopts foreign server changes only when
  // it's safe (no unsaved edits).
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const save = useMutation({
    mutationFn: async () => {
      const validated = resumeDataSchema.safeParse(data);
      if (!validated.success) {
        throw new Error(
          validated.error.issues
            .map((i) => `${i.path.join(".")}: ${i.message}`)
            .join("; "),
        );
      }
      return apiFetch<Application>(`/api/applications/${applicationId}`, {
        method: "PATCH",
        body: JSON.stringify({
          customized_json: validated.data,
          formatting,
          template_id: templateIdToApi(templateId),
        }),
      });
    },
    onSuccess: (result) => {
      // Our own save: adopt the resulting server snapshot WITHOUT the foreign-
      // change banner (the parent remounts on the new customized_json key once
      // the ["application"] invalidation below lands).
      onSaved();
      // Adopt the server's normalized formatting. Postgres JSONB re-orders keys
      // on the round-trip, so the local diff (built in schema-declaration order)
      // and the refetched value would otherwise never match — a formatting-only
      // save doesn't remount this component (it's keyed on customized_json), so
      // `dirty` would stay stuck true and gate Generate PDF / Re-score forever.
      setFormatting(
        (result.formatting as Partial<ResumeFormatting> | null) ?? null,
      );
      // Adopt the server's normalized template_id so the parent-held selection,
      // the dirty flag, and the render query param all agree after a save.
      onTemplateChange(templateIdFromApi(result.template_id));
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["application", applicationId] });
      qc.invalidateQueries({ queryKey: ["ats-compare", applicationId] });
      // Review mode reads the SAVED draft, so reverts (and any other edit) have
      // to re-diff or the list would keep offering changes that are already gone.
      qc.invalidateQueries({ queryKey: ["resume-diff", applicationId] });
      setRevertedKeys(new Set());
      toast.success("Saved. Rendering PDF…");
      // Auto-render so the PDF regenerates without a second click. `render`
      // lives in the parent, so it keeps running through the remount that the
      // ["application"] invalidation above triggers. `thenRescore` chains the
      // same mutation the manual "Re-score" button uses once the render
      // lands, so the tailored ATS score doesn't go stale silently after an
      // edit (`rescore` is lifted to the parent for the same reason).
      render.mutate({ thenRescore: true });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const busy = save.isPending || rescore.isPending || materializePending;
  const pdfHref = apiUrlForBrowserPdf(`/api/applications/${applicationId}/pdf`);
  const pdfFilename =
    application.pdf_path?.split(/[\\/]/).pop() ?? "tailored-resume.pdf";

  return (
    <>
      <EditorShell
        storageKey={STUDIO_STORAGE_KEY}
        // Matches the base studio: the preview header is the PDF's own
        // controls (download, open) and nothing else. The template picker moved
        // to the toolbar's tools group where base already had it, and "Generate
        // PDF" is gone — Save has always chained straight into render, so the
        // button could only be clicked when the PDF was ALREADY current (it was
        // disabled while dirty). The retry path for a failed render lives in the
        // ⋯ overflow, which is the only job it actually had.
        previewHeader={
          <>
            <Button
              variant="ghost"
              size="icon-sm"
              nativeButton={false}
              aria-label="Download PDF"
              disabled={!application.pdf_path}
              render={
                <a href={pdfHref} download={pdfFilename}>
                  <Download className="size-4" />
                </a>
              }
            />
            <Button
              variant="ghost"
              size="icon-sm"
              nativeButton={false}
              aria-label="Open PDF in new tab"
              disabled={!application.pdf_path}
              render={
                <a href={pdfHref} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4" />
                </a>
              }
            />
          </>
        }
        editor={
          <div className="flex flex-col gap-4">
            {serverChanged && dirty && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/[0.08] px-3 py-2 text-sm dark:border-amber-400/40 dark:bg-amber-400/[0.08]">
                <span className="text-amber-700 dark:text-amber-300">
                  This draft changed outside the editor.
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={async () => {
                    const ok = await confirm({
                      title: "Load the latest version?",
                      description:
                        "This replaces the editor with the newer saved copy and discards your unsaved edits. This can't be undone.",
                      confirmLabel: "Load latest",
                      destructive: true,
                    });
                    if (ok) onLoadLatest();
                  }}
                >
                  Load latest (discards your edits)
                </Button>
              </div>
            )}
            {/* Same PageHeader as the base-resume studio and every other route.
                Both studios already shared EditorShell; the header was the one
                part that had forked. */}
            <PageHeader
              leading={
                <IconButton
                  label="Back to application"
                  icon={<ArrowLeft className="size-4" />}
                  size="icon-sm"
                  className="mt-1.5 shrink-0"
                  nativeButton={false}
                  render={
                    <Link href={backHref} className="text-muted-foreground" />
                  }
                />
              }
              title="Tailored resume"
              subtitle={jobLabel}
              actions={
                <StudioToolbar
                  tools={
                    <>
                      {/* Same slot as the base studio's picker. Both studios
                          now auto-render on Save, so the template belongs with
                          the document tools rather than beside a render
                          button that no longer exists. */}
                      <TemplateSelect
                        value={templateId}
                        onChange={onTemplateChange}
                      />
                      {reviewAvailable && (
                        // `tonal` when pressed, not `default`: an active toggle
                        // used to render filled, so this bar could show two
                        // filled buttons at once and neither read as the
                        // primary action.
                        <Button
                          variant={review ? "tonal" : "outline"}
                          size="sm"
                          aria-pressed={review}
                          onClick={() => setReview((value) => !value)}
                        >
                          <GitCompare />
                          Review changes
                          {hunks.length > 0 && !review
                            ? ` (${hunks.length})`
                            : ""}
                        </Button>
                      )}
                      {/* The "Save your edits first" note used to be a bare
                          <span> sitting in the control row. A transient status
                          message is not a toolbar item — it belongs on the
                          control it explains, read at the moment it applies. */}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => rescore.mutate()}
                        disabled={busy || dirty}
                        title={
                          dirty
                            ? "Save your edits first. Re-scoring runs on the saved resume."
                            : undefined
                        }
                      >
                        {rescore.isPending ? (
                          <Loader2 className="animate-spin" />
                        ) : (
                          <RefreshCw />
                        )}
                        {rescore.isPending ? "Re-scoring…" : "Re-score"}
                      </Button>
                    </>
                  }
                  primary={
                    <Button
                      size="sm"
                      onClick={() => save.mutate()}
                      disabled={busy || !dirty}
                    >
                      {save.isPending && <Loader2 className="animate-spin" />}
                      {save.isPending ? "Saving…" : "Save"}
                    </Button>
                  }
                  overflow={
                    <StudioOverflowMenu
                      rawMode={rawMode}
                      onToggleRaw={() => setRawMode((r) => !r)}
                      onHistory={() => setHistoryOpen(true)}
                    >
                      {/* The recovery path, and the only job "Generate PDF"
                            ever really had: Save auto-renders, so the one case
                            a manual trigger covers is a render that FAILED —
                            without this, a failed render with nothing left to
                            edit would leave no way to retry (Save is disabled
                            when not dirty). */}
                        <DropdownMenuItem
                          disabled={busy || render.isPending || dirty}
                          onClick={() => render.mutate()}
                        >
                          <RefreshCw />
                          {/* Same verb as the job page's Resume tab, which is
                              the OTHER place this operation is offered:
                              generate when there is no PDF, regenerate when
                              there is. Two names for one action is how a
                              vocabulary forks. */}
                          {render.isPending
                            ? "Generating…"
                            : application.pdf_path
                              ? "Regenerate PDF"
                              : "Generate PDF"}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          variant="destructive"
                          disabled={busy}
                          onClick={async () => {
                            const ok = await confirm({
                              title: "Rebuild from base resume?",
                              description:
                                "This erases the tailored resume content, the rendered PDF, and any unsaved edits in the studio. This can't be undone.",
                              confirmLabel: "Rebuild from base",
                              destructive: true,
                            });
                            if (ok) onRebuild();
                          }}
                        >
                          <RefreshCw />
                          {materializePending
                            ? "Rebuilding…"
                            : "Rebuild from base"}
                        </DropdownMenuItem>
                    </StudioOverflowMenu>
                  }
                />
              }
            />

            {rawMode ? (
              <RawJsonToggle
                value={data}
                onChange={setData}
                onClose={() => setRawMode(false)}
              />
            ) : (
              <>
                {/* An OVERLAY, not a fork: the section editors below stay live
                    and editable while the change list is open. */}
                {showReview && (
                  <DiffReviewPanel
                    hunks={hunks}
                    revertedKeys={revertedKeys}
                    dirty={dirty}
                    onRevert={handleRevert}
                    coherence={coherence}
                    onCheckCoherence={handleCheckCoherence}
                    onApplyProposal={handleApplyProposal}
                    onApplyHygiene={handleApplyHygiene}
                  />
                )}
                <div className="grid gap-1.5 rounded-md">
                  <Label htmlFor="studio-summary">
                    Summary
                    {changeBadge("summary")}
                  </Label>
                  <Textarea
                    id="studio-summary"
                    rows={3}
                    value={data.summary ?? ""}
                    onChange={(e) =>
                      setData({ ...data, summary: e.target.value })
                    }
                  />
                </div>

                <Tabs defaultValue="contact">
                  {/* Wraps: seven section tabs do not fit a pane
                      that is a fraction of the window. */}
                  <TabsList className="h-auto flex-wrap">
                    <TabsTrigger value="contact">
                      Contact
                      {changeBadge("contact")}
                    </TabsTrigger>
                    <TabsTrigger value="skills">
                      Skills
                      {changeBadge("skills")}
                    </TabsTrigger>
                    <TabsTrigger value="experience">
                      Experience
                      {changeBadge("experience")}
                    </TabsTrigger>
                    <TabsTrigger value="projects">
                      Projects
                      {changeBadge("projects")}
                    </TabsTrigger>
                    <TabsTrigger value="education">
                      Education
                      {changeBadge("education")}
                    </TabsTrigger>
                    <TabsTrigger value="certifications">
                      Certifications
                      {changeBadge("certifications")}
                    </TabsTrigger>
                    <TabsTrigger value="extra">
                      Extra sections
                      {changeBadge("extra")}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="contact">
                    <ContactForm
                      value={data.contact}
                      onChange={(contact) => setData({ ...data, contact })}
                    />
                  </TabsContent>
                  <TabsContent value="skills">
                    <SkillsEditor
                      value={data.skills}
                      onChange={(skills) => setData({ ...data, skills })}
                    />
                  </TabsContent>
                  <TabsContent value="experience">
                    <ExperienceEditor
                      value={data.experience}
                      onChange={(experience) =>
                        setData({ ...data, experience })
                      }
                    />
                  </TabsContent>
                  <TabsContent value="projects">
                    <ProjectEditor
                      value={data.projects}
                      onChange={(projects) => setData({ ...data, projects })}
                    />
                  </TabsContent>
                  <TabsContent value="education">
                    <EducationEditor
                      value={data.education}
                      onChange={(education) => setData({ ...data, education })}
                    />
                  </TabsContent>
                  <TabsContent value="certifications">
                    <div className="grid gap-1.5">
                      <Label htmlFor="studio-certs">Certifications</Label>
                      <ChipListInput
                        id="studio-certs"
                        value={data.certifications}
                        onChange={(certifications) =>
                          setData({ ...data, certifications })
                        }
                        placeholder="Add certification…"
                      />
                    </div>
                  </TabsContent>
                  <TabsContent value="extra">
                    <ExtraSectionsEditor
                      value={data.extra_sections ?? []}
                      onChange={(extra_sections) =>
                        setData({ ...data, extra_sections })
                      }
                    />
                  </TabsContent>
                </Tabs>
              </>
            )}
          </div>
        }
        formattingPanel={
          <FormattingPanel
            value={formatting}
            onChange={setFormatting}
            supportedKeys={supportedFmtKeys}
            baseline={formattingBaseline}
            inherited={application.formatting == null}
            onRevertToBase={() => setFormatting(null)}
            collapsible={false}
          />
        }
        preview={
          <PdfPagesPreview
            basePath={`/api/applications/${applicationId}`}
            version={pdfNonce}
            emptyMessage="No PDF yet. Save your edits and it renders automatically."
          />
        }
      />
      <VersionHistorySheet
        kind="application"
        resumeKey={applicationId}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        onRestored={() =>
          qc.invalidateQueries({ queryKey: ["application", applicationId] })
        }
      />
    </>
  );
}
