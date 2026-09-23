"use client";

import { useEffect, useRef, useState } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Copy,
  Download,
  ExternalLink,
  Pencil,
  RefreshCw,
  Sparkles,
  Tag,
} from "lucide-react";
import { toast } from "sonner";

import { IconButton } from "@/components/icon-button";
import { KbSyncPill } from "@/components/kb-sync-pill";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { PageHeader } from "@/components/page-shell";
import { ContactForm } from "@/components/resume-editor/contact-form";
import { EditableTitle } from "@/components/resume-editor/editable-title";
import { EditorShell } from "@/components/resume-editor/editor-shell";
import { StudioOverflowMenu } from "@/components/resume-editor/studio-overflow";
import { StudioSaveButton } from "@/components/resume-editor/studio-save-button";
import { StudioToolbar } from "@/components/resume-editor/studio-toolbar";
import { EducationEditor } from "@/components/resume-editor/education-editor";
import { ExperienceEditor } from "@/components/resume-editor/experience-editor";
import { ExtraSectionsEditor } from "@/components/resume-editor/extra-sections-editor";
import { FormattingPanel } from "@/components/resume-editor/formatting-panel";
import { InstructSheet } from "@/components/resume-editor/instruct-sheet";
import { KbImportDrawer } from "@/components/resume-editor/kb-import-drawer";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { ProjectEditor } from "@/components/resume-editor/project-editor";
import {
  RawJsonToggle,
  useRawJsonDraft,
} from "@/components/resume-editor/raw-json-toggle";
import { SaveStatusText } from "@/components/resume-editor/save-status";
import { SkillsEditor } from "@/components/resume-editor/skills-editor";
import { HealthBadges } from "@/components/resume-health/health-badges";
import { VersionHistorySheet } from "@/components/resume-versions/version-history-sheet";
import {
  TemplateSelect,
  templateIdFromApi,
  templateIdToApi,
  useTemplateBaseline,
} from "@/components/templates/template-select";
import { Button } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import {
  RoleCategoryDialog,
  roleMenuLabel,
  useRoleCategories,
} from "@/components/role-category-picker";
import { ChipListInput } from "@/components/ui/chip-input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { type ResumeFormatting } from "@/lib/formatting";
import { notifyRenderNote } from "@/lib/render-note";
import { resumeDataSchema } from "@/lib/resume-schema";
import { emptyPreviewMessage, keepIfEdited, saveStatus } from "@/lib/studio";
import type { BaseResumeDetail, ResumeData } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The server record the form is in sync with, as one comparable string. */
function syncedSnapshotOf(record: BaseResumeDetail): string {
  return JSON.stringify({
    data: record.data,
    displayName: record.display_name ?? "",
    formatting: record.formatting ?? null,
    templateId: record.template_id ?? null,
  });
}

/** What a Save sends (the mutation's variables, so its response can tell edits made since). */
type BaseSaveSent = {
  data: ResumeData;
  displayName: string;
  formatting: Partial<ResumeFormatting> | null;
  templateId: string;
};

export function EditorBody({
  slug,
  initial,
}: {
  slug: string;
  initial: BaseResumeDetail;
}) {
  const qc = useQueryClient();
  const [data, setData] = useState<ResumeData>(initial.data);
  const [displayName, setDisplayName] = useState(initial.display_name ?? "");
  const [rawMode, setRawMode] = useState(false);
  const raw = useRawJsonDraft();
  const [importOpen, setImportOpen] = useState(false);
  const [instructOpen, setInstructOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [roleOpen, setRoleOpen] = useState(false);
  // Same shared vocabulary query the picker uses, for the menu item's label.
  const { data: roleCategories } = useRoleCategories();
  const [templateId, setTemplateId] = useState(
    templateIdFromApi(initial.template_id),
  );
  const [formatting, setFormatting] = useState<Partial<ResumeFormatting> | null>(
    (initial.formatting as Partial<ResumeFormatting> | null) ?? null,
  );
  const formattingBaseline = useTemplateBaseline(templateId);

  const { data: live } = useQuery({
    queryKey: ["base-resumes", slug],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`),
    initialData: initial,
  });


  // Snapshot of the server record the form is in sync with. Lets us adopt
  // external changes (e.g. edits made via the MCP server in another client)
  // without clobbering unsaved local edits — and prevents a later Save from
  // overwriting the newer server record with stale form state.
  const initialSyncedSnapshot = syncedSnapshotOf(initial);
  const lastSyncedRef = useRef(initialSyncedSnapshot);
  const [lastSyncedSnapshot, setLastSyncedSnapshot] = useState(
    initialSyncedSnapshot,
  );
  useEffect(() => {
    if (!live) return;
    const liveSnap = syncedSnapshotOf(live);
    const localSnap = JSON.stringify({
      data,
      displayName,
      formatting,
      templateId: templateIdToApi(templateId),
    });
    const serverMoved = liveSnap !== lastSyncedRef.current;
    if (serverMoved && localSnap === liveSnap) {
      // The form already holds what the server now has. A rename does this:
      // EditableTitle lifts the name, then PATCHes /identity and writes the
      // cache. Nothing to adopt, but the baseline must move, or the studio
      // reads the saved name as an unsaved edit.
      lastSyncedRef.current = liveSnap;
      setLastSyncedSnapshot(liveSnap);
    } else if (serverMoved && localSnap === lastSyncedRef.current && !raw.pending) {
      // Only adopt the server record when the user has no unsaved local edits,
      // typed JSON included: a later Apply would overwrite the adopted copy.
      // It adopts once the draft is applied or discarded.
      setData(live.data);
      setDisplayName(live.display_name ?? "");
      setFormatting(
        (live.formatting as Partial<ResumeFormatting> | null) ?? null,
      );
      setTemplateId(templateIdFromApi(live.template_id));
      lastSyncedRef.current = liveSnap;
      setLastSyncedSnapshot(liveSnap);
    }
  }, [live, data, displayName, formatting, templateId, raw.pending]);

  const buildPdfHref = (download: boolean) => {
    if (!live.pdf_path) return null;
    const params = new URLSearchParams();
    if (live.pdf_rendered_at) {
      const raw = live.pdf_rendered_at as string | Date;
      const ms =
        typeof raw === "string"
          ? Date.parse(raw)
          : raw instanceof Date
            ? raw.getTime()
            : NaN;
      if (!Number.isNaN(ms)) params.set("v", String(ms));
    }
    if (download) params.set("download", "1");
    const qs = params.toString();
    return apiUrlForBrowserPdf(
      `/api/base-resumes/${slug}/pdf${qs ? `?${qs}` : ""}`,
    );
  };
  const pdfHref = buildPdfHref(false);
  const pdfDownloadHref = buildPdfHref(true);

  const markSynced = (result: BaseResumeDetail) => {
    const snapshot = syncedSnapshotOf(result);
    lastSyncedRef.current = snapshot;
    setLastSyncedSnapshot(snapshot);
  };

  // Full adoption, for the paths gated on no unsaved edits (Ask for changes,
  // Import from Career KB). A Save takes the record field by field instead.
  const adoptBaseResumeDetail = (result: BaseResumeDetail) => {
    setData(result.data);
    setDisplayName(result.display_name ?? "");
    setFormatting(
      (result.formatting as Partial<ResumeFormatting> | null) ?? null,
    );
    setTemplateId(templateIdFromApi(result.template_id));
    markSynced(result);
  };

  const save = useMutation({
    mutationFn: async (sent: BaseSaveSent) => {
      const validated = resumeDataSchema.safeParse(sent.data);
      if (!validated.success) {
        throw new Error(
          validated.error.issues
            .map((i) => `${i.path.join(".")}: ${i.message}`)
            .join("; "),
        );
      }
      return apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`, {
        method: "PUT",
        body: JSON.stringify({
          display_name: sent.displayName || null,
          data: validated.data,
          template_id: templateIdToApi(sent.templateId),
          formatting: sent.formatting,
        }),
      });
    },
    onSuccess: (result, sent) => {
      // Adopt the server's normalized record so form, cache, and sync-snapshot
      // agree after a save, but only where nothing changed since the send.
      // The PUT renders inline, so a save runs for seconds, and an edit made
      // meanwhile stays and reads as unsaved.
      setData((cur) => keepIfEdited(cur, sent.data, result.data));
      setDisplayName((cur) =>
        keepIfEdited(cur, sent.displayName, result.display_name ?? ""),
      );
      setFormatting((cur) =>
        keepIfEdited(
          cur,
          sent.formatting,
          (result.formatting as Partial<ResumeFormatting> | null) ?? null,
        ),
      );
      setTemplateId((cur) =>
        keepIfEdited(cur, sent.templateId, templateIdFromApi(result.template_id)),
      );
      markSynced(result);
      qc.setQueryData(["base-resumes", slug], result);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      notifyRenderNote(result);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Recovery for a render that FAILED. Save is dirty-gated, so with nothing to
  // save it can no longer double as "render again". Mirrors the tailored
  // studio's ⋯ Regenerate PDF, against the base's own render endpoint (the
  // render IS the request, so a failure is a 400, never a persisted note).
  const regenerate = useMutation({
    mutationFn: () =>
      apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}/render`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      qc.setQueryData(["base-resumes", slug], result);
      // The gallery's "last render failed" badge reads the list.
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["pdf-preview"] });
      notifyRenderNote(result);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const currentSnapshot = JSON.stringify({
    data,
    displayName,
    formatting,
    templateId: templateIdToApi(templateId),
  });
  const hasUnsavedChanges = raw.pending || currentSnapshot !== lastSyncedSnapshot;
  // This flag already existed but only ever gated the KB-import button, so a
  // reload or a closed tab discarded the edits without a word.
  useLeaveGuard(hasUnsavedChanges);
  const status = saveStatus({
    dirty: hasUnsavedChanges,
    saving: save.isPending,
    rendering: regenerate.isPending,
    rescoring: false,
  });
  const canSave = hasUnsavedChanges && !save.isPending && !regenerate.isPending;
  // Applies a pending raw draft first (see the tailored studio's `onSave`).
  const onSave = () =>
    raw.commitThen(setData, (applied) =>
      save.mutate({ data: applied ?? data, displayName, formatting, templateId }),
    );

  return (
    <>
      <EditorShell
        previewStale={hasUnsavedChanges}
        previewHeader={
          pdfHref && (
            <>
              <Button
                variant="ghost"
                size="icon-sm"
                nativeButton={false}
                aria-label="Download PDF"
                render={
                  <a href={pdfDownloadHref ?? "#"} download={`${slug}.pdf`}>
                    <Download className="size-4" />
                  </a>
                }
              />
              <Button
                variant="ghost"
                size="icon-sm"
                nativeButton={false}
                aria-label="Open PDF in new tab"
                render={
                  <a href={pdfHref} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="size-4" />
                  </a>
                }
              />
            </>
          )
        }
        editor={
          <div className="flex flex-col gap-4">
            {/* Both groups wrap. The row carries six controls plus the
                template picker inside a pane that is only ~55% of the window
                once the preview is open, so a non-wrapping group ran off the
                edge and disappeared under the preview. */}
            {/* Same PageHeader as every other route, with the back button in
                the `leading` slot. The two resume studios (this one and the
                application's tailored studio) already share EditorShell; their
                headers were the one part that had forked. */}
            <PageHeader
              leading={
                <IconButton
                  label="Back to base resumes"
                  icon={<ArrowLeft className="size-4" />}
                  size="icon-sm"
                  className="mt-1.5 shrink-0"
                  nativeButton={false}
                  render={
                    <Link
                      href="/base-resumes"
                      className="text-muted-foreground"
                    />
                  }
                />
              }
              /* The title IS the display name — it is not a heading that
                 happens to echo a field. The old layout rendered this string
                 twice within ~100px: once as the <h1> and once as a "Display
                 name" input right below it, with the slug as a third identity
                 line between them. One place to read it, one place to change
                 it. */
              title={
                <EditableTitle
                  slug={slug}
                  value={displayName}
                  onChange={setDisplayName}
                />
              }
              /* The subtitle is the save-status line, NOT an identity line.
                 The header used to carry three identity lines saying the same
                 words for any resume whose name, slug and role agree — the
                 common case, since the slug is derived from the name and the
                 name from the role. The name is the title; the slug is in the
                 URL and on "Copy slug"; the role is the ⋯ menu's first item,
                 which NAMES its current value so it is still read without
                 opening anything. All three still write through PATCH
                 /identity rather than Save. */
              subtitle={<SaveStatusText status={status} />}
              actions={
                <StudioToolbar
                  status={
                    <>
                      <HealthBadges
                        kind="base"
                        resumeKey={slug}
                        reportHref={`/base-resumes/${slug}/health`}
                      />
                      {/* Was a full-width card above the editor. Both of these
                          answer "is this document in good standing", so they
                          belong to the same slot rather than to two rows. */}
                      <KbSyncPill slug={slug} />
                    </>
                  }
                  tools={
                    <TemplateSelect
                      value={templateId}
                      onChange={setTemplateId}
                    />
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
                      /* Props in the order the menu renders them: this item,
                         the shared pair, then `children`. First, and labelled
                         with its value: this is the only place the role is
                         legible now that the header shows the name alone, so
                         it is read as often as the two shared items are
                         used. */
                      leading={
                        <DropdownMenuItem onClick={() => setRoleOpen(true)}>
                          <Tag />
                          {roleMenuLabel(
                            live?.role_category ?? initial.role_category,
                            live?.role_label ?? initial.role_label,
                            roleCategories,
                          )}
                        </DropdownMenuItem>
                      }
                      rawMode={rawMode}
                      onToggleRaw={() =>
                        rawMode
                          ? raw.commitThen(setData, () => setRawMode(false))
                          : setRawMode(true)
                      }
                      onHistory={() => setHistoryOpen(true)}
                    >
                      <DropdownMenuItem
                        disabled={
                          hasUnsavedChanges ||
                          regenerate.isPending ||
                          save.isPending
                        }
                        onClick={() => regenerate.mutate()}
                      >
                        <RefreshCw />
                        {regenerate.isPending
                          ? "Generating…"
                          : live.pdf_path
                            ? "Regenerate PDF"
                            : "Generate PDF"}
                      </DropdownMenuItem>
                      {/* A free instruction against this document — an edit
                          or a question. Applying goes through PATCH /edits on
                          the SAVED record, so like the KB import it waits for
                          unsaved edits to be saved first rather than merging
                          into a form the server has not seen. */}
                      <DropdownMenuItem
                        disabled={hasUnsavedChanges}
                        onClick={() => setInstructOpen(true)}
                      >
                        <Sparkles />
                        Ask for changes…
                      </DropdownMenuItem>
                      {/* Moved out of the inline bar: it is the rarest thing
                          here and it is disabled whenever there are unsaved
                          edits, yet it used to sit first and most prominent. */}
                      <DropdownMenuItem
                        disabled={hasUnsavedChanges}
                        onClick={() => setImportOpen(true)}
                      >
                        <Download />
                        Import from Career KB
                      </DropdownMenuItem>
                      {/* The slug left the header; MCP tools and the on-disk
                          filename still speak it, so it stays one click away
                          rather than something to retype off the URL. Named
                          with its value, like the Role item above: "slug" is
                          developer vocabulary, and showing the value is what
                          tells a reader what they would be copying. */}
                      <DropdownMenuItem
                        onClick={() => {
                          navigator.clipboard
                            .writeText(slug)
                            .then(() => toast.success(`Copied ${slug}`))
                            .catch(() => toast.error("Could not copy slug"));
                        }}
                      >
                        <Copy />
                        {`Copy slug: ${slug}`}
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
                {/* Identity (display name, role) lives in the header now
                    — it names the document rather than being content inside it,
                    and it was the source of the duplicate "Display name" field
                    that used to sit here. */}

                <SummaryBlock
                  value={data.summary ?? ""}
                  onChange={(summary) => setData({ ...data, summary })}
                />

                <Tabs defaultValue="contact">
                  {/* Wraps: seven section tabs do not fit a pane
                      that is a fraction of the window. */}
                  <TabsList className="h-auto flex-wrap">
                    <TabsTrigger value="contact">Contact</TabsTrigger>
                    <TabsTrigger value="skills">Skills</TabsTrigger>
                    <TabsTrigger value="experience">Experience</TabsTrigger>
                    <TabsTrigger value="projects">Projects</TabsTrigger>
                    <TabsTrigger value="education">Education</TabsTrigger>
                    <TabsTrigger value="certifications">
                      Certifications
                    </TabsTrigger>
                    <TabsTrigger value="extra">Extra sections</TabsTrigger>
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
                      sourceSlug={slug}
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
                    <CertificationsBlock
                      value={data.certifications}
                      onChange={(certifications) =>
                        setData({ ...data, certifications })
                      }
                    />
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
            collapsible={false}
          />
        }
        preview={
          <PdfPagesPreview
            basePath={`/api/base-resumes/${slug}`}
            version={live.pdf_rendered_at as string | null}
            emptyMessage={emptyPreviewMessage(hasUnsavedChanges)}
          />
        }
      />
      <VersionHistorySheet
        kind="base"
        resumeKey={slug}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        onRestored={() =>
          qc.invalidateQueries({ queryKey: ["base-resumes", slug] })
        }
      />
      <RoleCategoryDialog
        slug={slug}
        roleCategory={live?.role_category ?? initial.role_category}
        roleLabel={live?.role_label ?? initial.role_label}
        open={roleOpen}
        onOpenChange={setRoleOpen}
      />
      <InstructSheet
        open={instructOpen}
        onOpenChange={setInstructOpen}
        targetSlug={slug}
        onApplied={(result) => {
          adoptBaseResumeDetail(result);
        }}
      />
      <KbImportDrawer
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={(result) => {
          adoptBaseResumeDetail(result);
        }}
        targetSlug={slug}
        targetData={data}
      />
    </>
  );
}

function SummaryBlock({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <div className="grid gap-2">
        <Label htmlFor="summary">Summary</Label>
        <Textarea
          id="summary"
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setEditing(false)}>
            Done
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div
      className={cn(
        "group/sum relative rounded-md border border-l-2 px-3 py-3",
        "border-border/0 hover:border-border/60",
      )}
    >
      <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
        Summary
      </div>
      <p className="text-foreground/90 pr-10 text-sm whitespace-pre-wrap">
        {value || (
          <span className="text-muted-foreground italic">No summary</span>
        )}
      </p>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="Edit summary"
        className="pointer-coarse:opacity-100 absolute top-2 right-2 opacity-0 transition-opacity group-hover/sum:opacity-100 focus-within:opacity-100"
        onClick={() => setEditing(true)}
      >
        <Pencil className="size-3.5" />
      </Button>
    </div>
  );
}

function CertificationsBlock({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <div className="grid gap-2">
        <Label htmlFor="certs">Certifications</Label>
        <ChipListInput
          id="certs"
          value={value}
          onChange={onChange}
          placeholder="Add certification…"
        />
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setEditing(false)}>
            Done
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="group/certs border-border/0 hover:border-border/60 relative rounded-md border px-3 py-3">
      {value.length > 0 ? (
        <ul className="text-foreground/90 ml-4 list-disc space-y-1 pr-10 text-sm">
          {value.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground pr-10 text-sm italic">
          No certifications
        </p>
      )}
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="Edit certifications"
        className="pointer-coarse:opacity-100 absolute top-2 right-2 opacity-0 transition-opacity group-hover/certs:opacity-100 focus-within:opacity-100"
        onClick={() => setEditing(true)}
      >
        <Pencil className="size-3.5" />
      </Button>
    </div>
  );
}
