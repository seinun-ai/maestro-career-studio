"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  MoreHorizontal,
  Pencil,
} from "lucide-react";
import { toast } from "sonner";

import { IconButton } from "@/components/icon-button";
import { useUnsavedChangesWarning } from "@/hooks/use-unsaved-changes-warning";
import { PageHeader } from "@/components/page-shell";
import { ContactForm } from "@/components/resume-editor/contact-form";
import { EditableTitle } from "@/components/resume-editor/editable-title";
import { EditorShell } from "@/components/resume-editor/editor-shell";
import { StudioToolbar } from "@/components/resume-editor/studio-toolbar";
import { EducationEditor } from "@/components/resume-editor/education-editor";
import { ExperienceEditor } from "@/components/resume-editor/experience-editor";
import { ExtraSectionsEditor } from "@/components/resume-editor/extra-sections-editor";
import { FormattingPanel } from "@/components/resume-editor/formatting-panel";
import { KbImportDrawer } from "@/components/resume-editor/kb-import-drawer";
import { PdfPagesPreview } from "@/components/resume-editor/pdf-pages-preview";
import { ProjectEditor } from "@/components/resume-editor/project-editor";
import { RawJsonToggle } from "@/components/resume-editor/raw-json-toggle";
import { SkillsEditor } from "@/components/resume-editor/skills-editor";
import { HealthBadges } from "@/components/resume-health/health-badges";
import { VersionHistorySheet } from "@/components/resume-versions/version-history-sheet";
import {
  TemplateSelect,
  templateIdFromApi,
  templateIdToApi,
  useSupportedFmtKeys,
  useTemplateDefaults,
} from "@/components/templates/template-select";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { RoleCategoryPicker } from "@/components/role-category-picker";
import { ChipListInput } from "@/components/ui/chip-input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import { FORMATTING_DEFAULTS, type ResumeFormatting } from "@/lib/formatting";
import { resumeDataSchema } from "@/lib/resume-schema";
import type { BaseResumeDetail, ResumeData } from "@/lib/types";
import { cn } from "@/lib/utils";

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
  const [importOpen, setImportOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [templateId, setTemplateId] = useState(
    templateIdFromApi(initial.template_id),
  );
  const [formatting, setFormatting] = useState<Partial<ResumeFormatting> | null>(
    (initial.formatting as Partial<ResumeFormatting> | null) ?? null,
  );
  const supportedFmtKeys = useSupportedFmtKeys(templateId);
  const templateDefaults = useTemplateDefaults(templateId);
  const formattingBaseline: ResumeFormatting = {
    ...FORMATTING_DEFAULTS,
    ...templateDefaults,
  };

  const { data: live } = useQuery({
    queryKey: ["base-resumes", slug],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`),
    initialData: initial,
  });


  // Snapshot of the server record the form is in sync with. Lets us adopt
  // external changes (e.g. edits made via the MCP server in another client)
  // without clobbering unsaved local edits — and prevents a later Save from
  // overwriting the newer server record with stale form state.
  const initialSyncedSnapshot = JSON.stringify({
    data: initial.data,
    displayName: initial.display_name ?? "",
    formatting: initial.formatting ?? null,
    templateId: initial.template_id ?? null,
  });
  const lastSyncedRef = useRef(initialSyncedSnapshot);
  const [lastSyncedSnapshot, setLastSyncedSnapshot] = useState(
    initialSyncedSnapshot,
  );
  useEffect(() => {
    if (!live) return;
    const liveSnap = JSON.stringify({
      data: live.data,
      displayName: live.display_name ?? "",
      formatting: live.formatting ?? null,
      templateId: live.template_id ?? null,
    });
    const localSnap = JSON.stringify({
      data,
      displayName,
      formatting,
      templateId: templateIdToApi(templateId),
    });
    // Only adopt the server record when the user has no unsaved local edits.
    if (
      liveSnap !== lastSyncedRef.current &&
      localSnap === lastSyncedRef.current
    ) {
      setData(live.data);
      setDisplayName(live.display_name ?? "");
      setFormatting(
        (live.formatting as Partial<ResumeFormatting> | null) ?? null,
      );
      setTemplateId(templateIdFromApi(live.template_id));
      lastSyncedRef.current = liveSnap;
      setLastSyncedSnapshot(liveSnap);
    }
  }, [live, data, displayName, formatting, templateId]);

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

  const adoptBaseResumeDetail = (result: BaseResumeDetail) => {
    setData(result.data);
    setDisplayName(result.display_name ?? "");
    setFormatting(
      (result.formatting as Partial<ResumeFormatting> | null) ?? null,
    );
    setTemplateId(templateIdFromApi(result.template_id));
    const snapshot = JSON.stringify({
      data: result.data,
      displayName: result.display_name ?? "",
      formatting: result.formatting ?? null,
      templateId: result.template_id ?? null,
    });
    lastSyncedRef.current = snapshot;
    setLastSyncedSnapshot(snapshot);
  };

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
      return apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`, {
        method: "PUT",
        body: JSON.stringify({
          display_name: displayName || null,
          data: validated.data,
          template_id: templateIdToApi(templateId),
          formatting,
        }),
      });
    },
    onSuccess: (result) => {
      // Adopt the server's normalized record so form, cache, and sync-snapshot
      // all agree after a save.
      adoptBaseResumeDetail(result);
      qc.setQueryData(["base-resumes", slug], result);
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast.success("Saved. PDF re-rendered.", {
        action: {
          label: "Download PDF",
          onClick: () =>
            window.open(apiUrlForBrowserPdf(`/api/base-resumes/${slug}/pdf`)),
        },
      });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const currentSnapshot = JSON.stringify({
    data,
    displayName,
    formatting,
    templateId: templateIdToApi(templateId),
  });
  const hasUnsavedChanges = currentSnapshot !== lastSyncedSnapshot;
  // This flag already existed but only ever gated the KB-import button, so a
  // reload or a closed tab discarded the edits without a word.
  useUnsavedChangesWarning(hasUnsavedChanges);

  return (
    <>
      <EditorShell
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
              /* Slug is an identifier, not prose — mono is the signal. Role
                 sits beside it because both are metadata ABOUT the document,
                 and both write through PATCH /identity rather than Save. */
              subtitle={
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{slug}</span>
                  <RoleCategoryPicker
                    slug={slug}
                    roleCategory={live?.role_category ?? initial.role_category}
                    roleLabel={live?.role_label ?? initial.role_label}
                    className="inline-flex h-6 min-h-6 w-fit flex-nowrap gap-0 px-1 py-0 text-xs leading-none"
                  />
                </span>
              }
              actions={
                <StudioToolbar
                  view={
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setRawMode((r) => !r)}
                    >
                      {rawMode ? "Form view" : "Raw JSON"}
                    </Button>
                  }
                  status={
                    <HealthBadges
                      kind="base"
                      resumeKey={slug}
                      reportHref={`/base-resumes/${slug}/health`}
                    />
                  }
                  tools={
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setHistoryOpen(true)}
                      >
                        History
                      </Button>
                      <TemplateSelect
                        value={templateId}
                        onChange={setTemplateId}
                      />
                    </>
                  }
                  primary={
                    <Button
                      onClick={() => save.mutate()}
                      disabled={save.isPending}
                    >
                      {save.isPending ? "Rendering PDF…" : "Save"}
                    </Button>
                  }
                  overflow={
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="More resume actions"
                          >
                            <MoreHorizontal />
                          </Button>
                        }
                      />
                      <DropdownMenuContent align="end">
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
                      </DropdownMenuContent>
                    </DropdownMenu>
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
                {/* Identity (display name, slug, role) lives in the header now
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
            supportedKeys={supportedFmtKeys}
            baseline={formattingBaseline}
            collapsible={false}
          />
        }
        preview={
          <PdfPagesPreview
            basePath={`/api/base-resumes/${slug}`}
            version={live.pdf_rendered_at as string | null}
            emptyMessage="No PDF rendered yet. Save the resume to render one."
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
