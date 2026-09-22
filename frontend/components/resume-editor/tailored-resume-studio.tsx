"use client";

import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
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
import { StudioSaveButton } from "@/components/resume-editor/studio-save-button";
import { StudioToolbar } from "@/components/resume-editor/studio-toolbar";
import { EducationEditor } from "@/components/resume-editor/education-editor";
import { ExperienceEditor } from "@/components/resume-editor/experience-editor";
import { ExtraSectionsEditor } from "@/components/resume-editor/extra-sections-editor";
import { FormattingPanel } from "@/components/resume-editor/formatting-panel";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { ProjectEditor } from "@/components/resume-editor/project-editor";
import {
  RawJsonToggle,
  useRawJsonDraft,
} from "@/components/resume-editor/raw-json-toggle";
import { SaveStatusText } from "@/components/resume-editor/save-status";
import { SkillsEditor } from "@/components/resume-editor/skills-editor";
import { VersionHistorySheet } from "@/components/resume-versions/version-history-sheet";
import {
  DEFAULT_TEMPLATE,
  TemplateSelect,
  templateIdFromApi,
  templateIdToApi,
  useTemplateBaseline,
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
import { overlayBaseline, type ResumeFormatting } from "@/lib/formatting";
import { notifyRenderNote } from "@/lib/render-note";
import { resumeDataSchema } from "@/lib/resume-schema";
import {
  adoptServerKey,
  emptyPreviewMessage,
  keepIfEdited,
  saveStatus,
  serverKey,
} from "@/lib/studio";
import type {
  Application,
  ApplicationDetail,
  BaseResumeDetail,
  HygieneFlag,
  RenderResult,
  ResumeData,
  ResumeDiffHunk,
} from "@/lib/types";

const STUDIO_STORAGE_KEY = "tailoredResumeStudio";

/**
 * What a Save sends, as one comparable string (see `unsaved` in StudioEditor).
 * By content, like `dirty`: key order is not an edit.
 */
function snapshotOf(
  d: ResumeData,
  f: Partial<ResumeFormatting> | null,
  t: string | null,
): string {
  return serverKey({ d, f: f ?? null, t });
}

/** What a Save sends (the mutation's variables, so its response can tell edits made since). */
type SaveSent = {
  data: ResumeData;
  formatting: Partial<ResumeFormatting> | null;
  templateId: string;
};

/**
 * A `serverKey` back into resume data, or null when absent or invalid. One
 * parse for the adopted copy and for a Save's response, so the two compare
 * equal when their content does.
 */
function parseResumeData(key: string): ResumeData | null {
  if (key === "") return null;
  let raw: unknown;
  try {
    raw = JSON.parse(key) as unknown;
  } catch {
    return null;
  }
  const parsed = resumeDataSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

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

  // Template lives here, beside `render`, which reads it for the query param.
  const [templateId, setTemplateId] = useState(
    templateIdFromApi(application.template_id),
  );

  // The render mutation and its cache-buster nonce live here (not in
  // StudioEditor) so a remount of the editor (Load latest, Rebuild, a foreign
  // edit adopted while clean) cannot tear down a render the Save chain started.
  const [pdfNonce, setPdfNonce] = useState(0);

  // Lifted alongside `render` (below), for the same reason: the post-save
  // auto re-score must outlive a remount mid-chain. This is the exact same
  // mutation the manual "Re-score" button uses — reused, not duplicated.
  const rescore = useMutation({
    mutationFn: () =>
      runAtsScoreTarget(jobId, "application", applicationId, "tailored"),
    // The variables carry the caller's `announce` flag and nothing the request
    // needs, so they are typed here, where they are read.
    onSuccess: (_data, opts: { announce?: boolean } | undefined) => {
      qc.invalidateQueries({ queryKey: ["ats-compare", applicationId] });
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
      // Only the manual Re-score confirms. The Save chain reports through the
      // header's status line, not a third toast.
      if (opts?.announce) toast.success("Tailored resume re-scored");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const render = useMutation({
    mutationFn: (opts?: { thenRescore?: boolean }) =>
      apiFetch<RenderResult>(
        `/api/applications/${applicationId}/render${
          templateId !== DEFAULT_TEMPLATE
            ? `?template_id=${encodeURIComponent(templateId)}`
            : ""
        }`,
        { method: "POST" },
      ),
    onSuccess: (data, opts) => {
      notifyRenderNote(data);
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
      if (opts?.thenRescore) rescore.mutate({ announce: false });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Dirty-guard (SYSTEM.md §12). Server copies compare by `serverKey`
  // (sorted-key JSON): the query cache keeps the old key order in every
  // subtree whose content did not change. The editor starts from the ADOPTED
  // key, not the live one, and `adoptServerKey` decides what a new live key
  // does: one our own Save returned moves the baseline in place; anyone
  // else's replaces the content when the editor is clean (or on a confirmed
  // Rebuild), and over unsaved edits keeps the editor and shows the banner.
  const customizedKey = useMemo(
    () => serverKey(application.customized_json),
    [application.customized_json],
  );
  const [adoptedKey, setAdoptedKey] = useState(customizedKey);
  // Remounts StudioEditor. Bumped only when a server copy REPLACES the
  // editor's content. Our own Save moves the baseline in place, so the
  // working copy, focus, tab, scroll, Formatting panel and status line
  // survive it.
  const [editorGen, setEditorGen] = useState(0);
  // Keys our own Saves returned that the server has not shown us yet.
  const ownKeys = useRef<string[]>([]);
  // A Rebuild's key: the user already agreed to lose unsaved edits.
  const forcedKey = useRef<string | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const onDirtyChange = useCallback((dirty: boolean) => setEditorDirty(dirty), []);

  // A layout effect: the refetch renders with the new live key before this
  // runs, and in that render `serverChanged && dirty` holds. Adopting before
  // paint keeps our own Save from flashing the banner for a frame.
  useLayoutEffect(() => {
    const next = adoptServerKey({
      live: customizedKey,
      adopted: adoptedKey,
      own: ownKeys.current,
      dirty: editorDirty,
      forced: forcedKey.current,
    });
    ownKeys.current = next.own;
    if (next.action === "none") return;
    // The server moved past whatever a Rebuild armed; never leave it armed.
    forcedKey.current = null;
    // "banner": keep the editor; `serverChanged` shows Load latest.
    if (next.action === "banner") return;
    setAdoptedKey(customizedKey);
    if (next.action === "remount") setEditorGen((g) => g + 1);
  }, [customizedKey, adoptedKey, editorDirty]);

  /** Replace the editor's content with the server copy `key` (a remount). */
  const replaceEditor = (key: string) => {
    ownKeys.current = [];
    forcedKey.current = null;
    setAdoptedKey(key);
    setEditorGen((g) => g + 1);
  };

  // The editor initializes from the adopted snapshot, not the live one.
  const adoptedData = useMemo(() => parseResumeData(adoptedKey), [adoptedKey]);
  const serverChanged = customizedKey !== "" && customizedKey !== adoptedKey;

  const materialize = useMutation({
    mutationFn: () =>
      apiFetch<ApplicationDetail>(
        `/api/applications/${applicationId}/materialize-resume`,
        { method: "POST" },
      ),
    onSuccess: (result) => {
      const key = serverKey(result.customized_json);
      // The adoption effect runs only when a key MOVES. A Rebuild whose
      // content equals the adopted copy, or the live one, moves nothing, yet
      // the user confirmed losing their edits: replace the editor here.
      // Otherwise the refetch brings the key, and the effect lets it win.
      if (key === adoptedKey || key === customizedKey) replaceEditor(key);
      else forcedKey.current = key;
      // The response IS the page's query data (ApplicationDetail). Seeding the
      // cache moves the live key now: before the refetch landed, the remounted
      // (clean) editor adopted the stale copy a banner was about, and painted it.
      qc.setQueryData(["application", applicationId], result);
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
      key={editorGen}
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
      onLoadLatest={() => replaceEditor(customizedKey)}
      onDirtyChange={onDirtyChange}
      onSaved={(key) => {
        // A formatting-only Save returns the adopted key: queueing it would
        // leave an entry no refetch consumes.
        if (key !== adoptedKey) ownKeys.current = [...ownKeys.current, key];
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
  onTemplateChange: Dispatch<SetStateAction<string>>;
  // Lifted to TailoredResumeStudio so they survive a remount mid-chain.
  render: {
    mutate: (opts?: { thenRescore?: boolean }) => void;
    isPending: boolean;
  };
  rescore: {
    mutate: (opts?: { announce?: boolean }) => void;
    isPending: boolean;
  };
  pdfNonce: number;
  // Dirty-guard wiring (see TailoredResumeStudio): the parent adopts newer
  // server snapshots; this editor reports its dirty state up, hands up the key
  // each of its own saves returned, and shows a reload banner when a foreign
  // change arrives while dirty.
  serverChanged: boolean;
  onLoadLatest: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (key: string) => void;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const applicationId = application.id;

  const [data, setData] = useState<ResumeData>(initialData);
  const [rawMode, setRawMode] = useState(false);
  const raw = useRawJsonDraft();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [formatting, setFormatting] = useState<Partial<ResumeFormatting> | null>(
    (application.formatting as Partial<ResumeFormatting> | null) ?? null,
  );
  // The application inherits the base resume's formatting (backend merges
  // schema <- template default <- base <- application). Fetch the base so the
  // panel anchors on the *inherited* values and only stores genuine overrides of
  // them. The panel stays locked until BOTH layers are in: an edit diffed
  // against the template layer alone drops an override equal to it.
  const templateBaseline = useTemplateBaseline(templateId);
  const baseResume = useQuery({
    queryKey: ["base-resumes", application.base_resume],
    queryFn: () =>
      apiFetch<BaseResumeDetail>(
        `/api/base-resumes/${application.base_resume}`,
      ),
  });
  const formattingBaseline = overlayBaseline(
    templateBaseline,
    baseResume,
    "the base resume's formatting",
  );


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
      <span className="bg-secondary-container text-on-secondary-container ml-1 rounded-full px-1.5 text-[10px] font-medium tabular-nums">
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

  // Dirty-state: the local working copy differs from the adopted server copy.
  // `initialData` is that copy, parsed. A remount (a copy that replaces the
  // content) starts clean; our own Save instead moves `initialData` in place
  // once its refetch lands, and `data` already holds the saved copy by then.
  const initialSerialized = useMemo(
    () => JSON.stringify(initialData),
    [initialData],
  );
  // Formatting can change independently of `customized_json`, so it feeds the
  // dirty flag too — otherwise a formatting-only edit couldn't be saved. The
  // baseline is the server value (`application.formatting`); an invalidated
  // application query after Save updates it, clearing the flag. Compared by
  // content: the panel emits keys in its own order, and a stored override
  // (Postgres-migrated, MCP-written) may hold the same values in another, so
  // moving a knob back to its stored value read as an unsaved edit.
  const serverFormatting = serverKey(application.formatting);
  // A template change alone is also a saveable edit — otherwise the choice could
  // be rendered with (via the render query param) but never persisted.
  const serverTemplateId = application.template_id ?? null;
  // Typed JSON not yet applied is an edit too: without it the leave-page
  // warning stayed quiet and a foreign edit remounted over the draft.
  const dirty = useMemo(
    () =>
      raw.pending ||
      JSON.stringify(data) !== initialSerialized ||
      serverKey(formatting) !== serverFormatting ||
      templateIdToApi(templateId) !== serverTemplateId,
    [
      raw.pending,
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

  // What our own last Save stored, as taken from its response. Between that
  // Save landing and the refetch that moves the baseline, `dirty` still
  // compares against the PRE-save server values; this keeps the status line,
  // Save and the stale strip from reporting the save we just made as unsaved.
  // An edit made after the Save differs from it and reads as unsaved at once.
  // `dirty` itself stays as it is: the parent's adoption guard and the
  // leave-page warning read it.
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);
  // Before the first Save there is nothing to compare, so `unsaved` is `dirty`.
  // A pending raw draft is unsaved whatever the snapshot says.
  const unsaved =
    raw.pending ||
    (dirty &&
      (savedSnapshot === null ||
        snapshotOf(data, formatting, templateIdToApi(templateId)) !==
          savedSnapshot));

  const save = useMutation({
    mutationFn: async (sent: SaveSent) => {
      const validated = resumeDataSchema.safeParse(sent.data);
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
          formatting: sent.formatting,
          template_id: templateIdToApi(sent.templateId),
        }),
      });
    },
    onSuccess: (result, sent) => {
      // Ours: the parent moves this editor's baseline to this key in place
      // once the refetch lands (no banner, no remount).
      const key = serverKey(result.customized_json);
      onSaved(key);
      // Take the server's normalized copies (the PATCH re-dumps the draft),
      // but only where nothing changed since the send: an edit made while the
      // save ran stays, and reads as unsaved. The snapshot applies the same
      // template normalisation the next render does, so an untouched template
      // compares equal.
      const savedData = parseResumeData(key) ?? sent.data;
      const savedFormatting =
        (result.formatting as Partial<ResumeFormatting> | null) ?? null;
      const savedTemplateId = templateIdFromApi(result.template_id);
      setData((cur) => keepIfEdited(cur, sent.data, savedData));
      setFormatting((cur) => keepIfEdited(cur, sent.formatting, savedFormatting));
      onTemplateChange((cur) => keepIfEdited(cur, sent.templateId, savedTemplateId));
      setSavedSnapshot(
        snapshotOf(savedData, savedFormatting, templateIdToApi(savedTemplateId)),
      );
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["application", applicationId] });
      qc.invalidateQueries({ queryKey: ["ats-compare", applicationId] });
      // Review mode reads the SAVED draft, so reverts (and any other edit) have
      // to re-diff or the list would keep offering changes that are already gone.
      qc.invalidateQueries({ queryKey: ["resume-diff", applicationId] });
      setRevertedKeys(new Set());
      // Auto-render so the PDF regenerates without a second click. `render`
      // lives in the parent, so a remount mid-chain cannot tear it down.
      // `thenRescore` chains the same mutation the manual "Re-score" button
      // uses once the render lands, so the tailored ATS score doesn't go stale
      // silently after an edit (`rescore` is lifted for the same reason).
      render.mutate({ thenRescore: true });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const busy = save.isPending || rescore.isPending || materializePending;
  const status = saveStatus({
    dirty: unsaved,
    saving: save.isPending,
    rendering: render.isPending,
    rescoring: rescore.isPending,
  });
  const canSave = unsaved && !busy;
  // Applies a pending raw draft first and saves exactly that (`setData` has
  // not landed yet); an invalid draft saves nothing and the pane says why.
  const onSave = () =>
    raw.commitThen(setData, (applied) =>
      save.mutate({ data: applied ?? data, formatting, templateId }),
    );
  const pdfHref = apiUrlForBrowserPdf(`/api/applications/${applicationId}/pdf`);
  const pdfFilename =
    application.pdf_path?.split(/[\\/]/).pop() ?? "tailored-resume.pdf";

  return (
    <>
      <EditorShell
        storageKey={STUDIO_STORAGE_KEY}
        previewStale={unsaved}
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
              subtitle={
                <span className="inline-flex flex-wrap items-center gap-x-2">
                  <span>{jobLabel}</span>
                  <span aria-hidden="true">·</span>
                  <SaveStatusText status={status} />
                </span>
              }
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
                        // primary action. The tonal fill is quiet, so the
                        // check (M3's selected-chip mark) is what says "on".
                        <Button
                          variant={review ? "tonal" : "outline"}
                          size="sm"
                          aria-pressed={review}
                          onClick={() => setReview((value) => !value)}
                        >
                          {review ? <Check /> : <GitCompare />}
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
                        onClick={() => rescore.mutate({ announce: true })}
                        disabled={busy || render.isPending || unsaved}
                        // No re-score while a render is out: the save chain
                        // re-scores itself when it lands. The gate reads
                        // `unsaved`, same as the hint, so the post-save gap
                        // does not block a re-score of work already saved.
                        title={
                          unsaved
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
                    <StudioSaveButton
                      onSave={onSave}
                      canSave={canSave}
                      pending={save.isPending}
                    />
                  }
                  overflow={
                    <StudioOverflowMenu
                      rawMode={rawMode}
                      onToggleRaw={() =>
                        rawMode
                          ? raw.commitThen(setData, () => setRawMode(false))
                          : setRawMode(true)
                      }
                      onHistory={() => setHistoryOpen(true)}
                    >
                      {/* The recovery path, and the only job "Generate PDF"
                            ever really had: Save auto-renders, so the one case
                            a manual trigger covers is a render that FAILED —
                            without this, a failed render with nothing left to
                            edit would leave no way to retry (Save is disabled
                            when nothing is unsaved). */}
                        <DropdownMenuItem
                          disabled={busy || render.isPending || unsaved}
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
                {...raw.bind}
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
                    dirty={unsaved}
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
            emptyMessage={emptyPreviewMessage(unsaved)}
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
