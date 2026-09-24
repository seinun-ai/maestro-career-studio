"use client";

import { useId, useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { KB_KIND_LABELS } from "@/components/career/career-labels";
import { Dropzone, type DropzoneRejection } from "@/components/setup/dropzone";
import { useFocusOnNextCommit, useOpenerReturn } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";

import { useRoleCategories } from "@/components/role-category-picker";
import {
  favoredRoleFromTag,
  identityFromFavoredRole,
  RolePicker,
} from "@/components/role-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { notifyRenderNote } from "@/lib/render-note";
import { uniqueSlug } from "@/lib/slug";
import { acceptedFilesHint, RESUME_FILE_ACCEPT } from "@/lib/upload-accept";
import {
  baseResumeLabel,
  type BaseResumeDetail,
  type BaseResumeSummary,
  type FavoredRole,
  type KBEntitySummary,
  type RoleCategory,
  type RoleMatch,
} from "@/lib/types";

const EMPTY_DATA = {
  contact: { name: "", email: "", phone: "", location: "", links: [] },
  summary: "",
  skills: [],
  experience: [],
  projects: [],
  education: [],
  certifications: [],
};

/** Certifications render as a bare title and education from institution,
 *  degree and dates — neither needs bullets to appear on a resume. */
function rendersWithoutPoints(kind: KBEntitySummary["kind"]) {
  return kind === "certification" || kind === "education";
}

type Plan = {
  include: string[];
  exclude: { id: string; title: string; reason: string }[];
  summary: string;
};

type Mode = "kb" | "existing" | "file" | "blank";

/** What Create still needs, per tab, in the order the form asks for it. */
function createBlockedReason(
  mode: Mode,
  form: { tag: unknown; selected: ReadonlySet<string>; source: string; file: File | null; name: string },
): string {
  if (mode === "kb") return form.tag ? "Choose at least one item to include." : "Choose a target role to create it.";
  if (mode === "existing") return "Choose a resume to copy.";
  if (mode === "file") return "Choose a file to create it.";
  return form.name.trim() ? "" : "Enter a name to create it.";
}

const NO_ROLES: RoleCategory[] = [];

const IMPORT_MAX_BYTES = 10 * 1024 * 1024;

/**
 * One dialog for every way a base resume comes into existence.
 *
 * The Career KB lane is the interesting one: a free instruction plans WHICH
 * knowledge-base entries belong on the resume and drafts the summary, and the
 * result is shown for review before anything is created. Bullet wording is
 * never touched — approved points compose verbatim, and rewriting them is the
 * KB adapt flow's job, where changes carry provenance and need approval.
 */
export function NewBaseResumeDialog({
  open,
  onOpenChange,
  initialMode = "kb",
  initialRole,
  existingResumes,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialMode?: Mode;
  /** Pre-select a target role, e.g. from a suggested-base prompt: a catalog
   *  key with its label, which the picker shows and a create sends. */
  initialRole?: { role_category: string; label: string };
  existingResumes: BaseResumeSummary[];
}) {
  // Lifted only so a backdrop/Esc close cannot yank the dialog mid-create.
  const [busy, setBusy] = useState(false);
  // The draft is kept across close: the popup stays mounted, so a typed name,
  // a picked selection and a plan the model is still writing all survive Esc
  // or an overlay click. Start over bumps the key, the one way to clear it.
  const [formGen, setFormGen] = useState(0);
  // Start over unmounts the button that was pressed; focus goes to the new
  // form's first field instead of falling to the page.
  const popupRef = useRef<HTMLDivElement>(null);
  const focusNext = useFocusOnNextCommit();
  // Kept mounted, the dialog keeps what the role picker's list recorded inside
  // it: Base UI's default return focused that hidden element. Every close
  // returns to what opened it.
  const returnToOpener = useOpenerReturn(open);
  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent size="lg" keepMounted ref={popupRef} finalFocus={returnToOpener}>
        <DialogHeader>
          <DialogTitle>New base resume</DialogTitle>
          <DialogDescription>
            Start from your career history, a copy, a file or a blank page.
          </DialogDescription>
        </DialogHeader>
        <NewBaseResumeForm
          key={formGen}
          open={open}
          onStartOver={() => {
            setFormGen((g) => g + 1);
            focusNext(popupRef);
          }}
          onOpenChange={onOpenChange}
          onBusyChange={setBusy}
          initialMode={initialMode}
          initialRole={initialRole}
          existingResumes={existingResumes}
        />
      </DialogContent>
    </Dialog>
  );
}

function NewBaseResumeForm({
  open,
  onStartOver,
  onOpenChange,
  onBusyChange,
  initialMode,
  initialRole,
  existingResumes,
}: {
  open: boolean;
  onStartOver: () => void;
  onOpenChange: (open: boolean) => void;
  onBusyChange: (busy: boolean) => void;
  initialMode: Mode;
  initialRole?: { role_category: string; label: string };
  existingResumes: BaseResumeSummary[];
}) {
  const router = useRouter();
  const qc = useQueryClient();
  // The form stays mounted while closed: the vocabulary is fetched on open.
  // The pickers get it from here ([] while it loads), so none fetches it
  // itself behind the closed dialog.
  const roles = useRoleCategories({ enabled: open });
  const roleCategories = roles.data ?? NO_ROLES;

  const [mode, setMode] = useState<Mode>(initialMode);
  const [name, setName] = useState("");
  // ALL three tabs share the free-text tag picker now. The KB tab's plan
  // endpoint still wants a coarse key, derived on demand by coarseFromTag —
  // one picker state, not a parallel kbRole that could disagree with it.
  const [initialTag] = useState<FavoredRole | null>(() =>
    initialRole ? { role: initialRole.role_category, label: initialRole.label, category: null } : null,
  );
  const [tag, setTag] = useState<FavoredRole | null>(initialTag);
  const [nameMatchApplied, setNameMatchApplied] = useState(false);
  const pendingNameMatch = useRef<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [source, setSource] = useState("");
  // The file lane: one resume file, parsed straight into a new base. Kept
  // apart from the onboarding import (which also feeds the Career KB and names
  // bases after their files) — here the user names the resume and the KB is
  // left alone.
  const [file, setFile] = useState<File | null>(null);
  const [fileRejected, setFileRejected] = useState<DropzoneRejection[]>([]);
  const slugsTaken = existingResumes.map((r) => r.slug);
  // Per instance: Getting started keeps one form per suggestion mounted at
  // once, and a fixed id would name the first (hidden) form's field.
  const fieldId = useId();
  const ids = {
    name: `${fieldId}-name`,
    nameHint: `${fieldId}-name-hint`,
    role: `${fieldId}-role`,
    instruction: `${fieldId}-instruction`,
    instructionHint: `${fieldId}-instruction-hint`,
    summary: `${fieldId}-summary`,
    summaryHint: `${fieldId}-summary-hint`,
    source: `${fieldId}-source`,
    copyRole: `${fieldId}-copy-role`,
    blocked: `${fieldId}-blocked`,
  };

  // The coarse key a FavoredRole implies, for the two KB calls that need one.
  // A confirmed mapping wins; a catalog pick resolves through the catalog (a
  // coarse key is itself, a specific role finds its parent group); unmapped
  // free text is `other` — the projection the server would store anyway.
  const coarseFromTag = (entry: FavoredRole | null): string => {
    if (!entry) return "";
    if (entry.category) return entry.category;
    if (entry.role) {
      const parent = roleCategories.find(
        (c) => c.key === entry.role || c.roles.some((r) => r.key === entry.role),
      );
      return parent?.key ?? "";
    }
    return "other";
  };

  const sourceResume = existingResumes.find((r) => r.slug === source);
  const inheritedTag = sourceResume
    ? favoredRoleFromTag(
        sourceResume.role_category,
        sourceResume.role_label,
        roles.data,
      )
    : null;

  const entities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => apiFetch<KBEntitySummary[]>("/api/kb/entities"),
    // The form stays mounted while closed; it fetches nothing until opened.
    enabled: open && mode === "kb",
  });
  // Experience and projects render FROM their bullets, so one with no approved
  // points would be an empty entry. Certifications render as a bare title and
  // education from institution/degree/dates, so those are fine at zero.
  // Only approved bullets go on the new resume: drafts and Not used ones are
  // not counted (`point_count` holds all three).
  const approvedCount = (e: KBEntitySummary) => e.approved_count;
  const selectable = (entities.data ?? []).filter(
    (e) =>
      e.status !== "archived" &&
      (approvedCount(e) > 0 || rendersWithoutPoints(e.kind)),
  );

  const done = (created: BaseResumeDetail) => {
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["setup-status"] });
    notifyRenderNote(created);
    if (created.parse_warnings && created.parse_warnings.length > 0) {
      // The parser dropped rows it could not read rather than failing the
      // file; the user should know what to look for in the editor.
      toast.warning(`Imported. ${created.parse_warnings.join(" ")} Check the resume in the editor.`);
    }
    onOpenChange(false);
    router.push(`/base-resumes/${created.slug}`);
  };

  const proposePlan = useMutation({
    mutationFn: () =>
      apiFetch<Plan>("/api/base-resumes/from-kb/plan", {
        method: "POST",
        body: JSON.stringify({ role_category: coarseFromTag(tag), instruction }),
      }),
    onSuccess: (result) => {
      setPlan(result);
      setSelected(new Set(result.include));
      setSummary(result.summary);
      if (result.include.length === 0) {
        toast.warning("No suggestions for this role. Pick items below.");
      }
    },
    onError: (err: Error) => toast.error(couldnt("suggest items", err)),
  });
  // One plan per click: a double click paid for two.
  const proposeOnce = useSingleFlight(proposePlan.mutate);

  const matchName = (typedName: string) => {
    const q = typedName.trim();
    if (!q) {
      pendingNameMatch.current = null;
      return;
    }
    pendingNameMatch.current = q;
    apiFetch<RoleMatch>(
      `/api/role-categories/match?q=${encodeURIComponent(q)}`,
    )
      .then((match) => {
        if (pendingNameMatch.current !== q || match.confidence === "none") {
          return;
        }
        // Display-side only: show the hit in the tag picker. Create sends
        // whatever the user left visible — never silent.
        const next: FavoredRole =
          match.role !== null
            ? {
                role: match.role,
                label: match.label,
                category: match.category,
              }
            : {
                role: null,
                label: match.label || q,
                category: match.category,
              };
        // Nested catalog roles are not storable as role_category; prefer the
        // parent category chip when the match resolved one.
        if (match.role !== null && match.category !== null) {
          const parent = roles.data?.find((c) => c.key === match.category);
          setTag({
            role: match.category,
            label: parent?.label ?? match.label,
            category: null,
          });
        } else {
          setTag(next);
        }
        setNameMatchApplied(true);
      })
      .catch(() => undefined);
  };

  /** One request per mode; everything around it (busy, errors, navigate) is
   *  identical, so it stays a single mutation. */
  const request = async () => {
    const display = name.trim() || null;
    if (mode === "kb") {
      return apiFetch<BaseResumeDetail>("/api/base-resumes/from-kb", {
        method: "POST",
        body: JSON.stringify({
          display_name: display,
          // The pair, not just the coarse key: a free-text tag survives on
          // the created resume, and the server's exact-collapse handles a
          // catalog label. See identityFromFavoredRole for the shape.
          role_label: identityFromFavoredRole(tag).role_label,
          role_category: coarseFromTag(tag),
          entity_ids: Array.from(selected),
          summary,
        }),
      });
    }
    if (mode === "file") {
      if (!file) throw new Error("Choose a resume file first.");
      const form = new FormData();
      form.append("file", file);
      // The server names the resume after the file when the name is blank and
      // derives a free slug either way; a typed name also picks the slug the
      // other lanes would.
      if (display) {
        form.append("display_name", display);
        form.append("slug", uniqueSlug(display, slugsTaken));
      }
      const identity = identityFromFavoredRole(tag);
      if (identity.role_category) form.append("role_category", identity.role_category);
      if (identity.role_label) form.append("role_label", identity.role_label);
      return apiFetch<BaseResumeDetail>("/api/base-resumes/import", {
        method: "POST",
        body: form,
      });
    }
    if (mode === "existing") {
      const created = await apiFetch<BaseResumeDetail>(
        `/api/base-resumes/${source}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify({
            new_slug: uniqueSlug(name || `${source} copy`, slugsTaken),
            new_display_name: display,
          }),
        },
      );
      // Duplicate inherits the source tag; PATCH identity with whatever the
      // user left visible (inherited, match pre-fill, or a manual edit).
      const body = identityFromFavoredRole(tag);
      const inherited = identityFromFavoredRole(inheritedTag);
      if (
        body.role_label !== inherited.role_label ||
        (body.role_category ?? null) !== (inherited.role_category ?? null)
      ) {
        const tagged = await apiFetch<BaseResumeDetail>(
          `/api/base-resumes/${created.slug}/identity`,
          {
            method: "PATCH",
            body: JSON.stringify(body),
          },
        );
        // Declaring a role deliberately does not re-render, so that response
        // carries no render note. Keep the duplicate's, or the fallback that
        // just rendered this resume goes unsaid on exactly this path.
        return { ...tagged, render_note: created.render_note };
      }
      return created;
    }
    const tagBody = identityFromFavoredRole(tag);
    return apiFetch<BaseResumeDetail>("/api/base-resumes", {
      method: "POST",
      body: JSON.stringify({
        slug: uniqueSlug(name, slugsTaken),
        display_name: display,
        data: EMPTY_DATA,
        ...(tag
          ? tagBody
          : {}),
      }),
    });
  };

  const create = useMutation({
    mutationFn: request,
    onMutate: () => onBusyChange(true),
    onSuccess: done,
    onError: (err: Error) => toast.error(couldnt("create the resume", err)),
    onSettled: () => onBusyChange(false),
  });

  const busy = create.isPending;

  const canCreate =
    mode === "kb"
      ? Boolean(tag) && selected.size > 0
      : mode === "existing"
        ? Boolean(source)
        : mode === "file"
          ? Boolean(file)
          : Boolean(name.trim());

  const submit = useSingleFlight(create.mutate);
  // Why Create is off, said beside it: a dimmed button alone never said.
  const blocked = busy || canCreate ? null : createBlockedReason(mode, { tag, selected, source, file, name });

  // What Start over would throw away. Switching tabs is not a draft.
  const touched =
    Boolean(name || instruction || selected.size || plan || source || file) ||
    tag !== initialTag;

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectSource = (slug: string) => {
    setSource(slug);
    const resume = existingResumes.find((r) => r.slug === slug);
    setTag(
      resume
        ? favoredRoleFromTag(resume.role_category, resume.role_label, roles.data)
        : null,
    );
    setNameMatchApplied(false);
  };

  const clearNameMatch = () => {
    setTag(inheritedTag);
    setNameMatchApplied(false);
  };

  return (
    <>
        <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <TabsList>
            <TabsTrigger value="kb">From career history</TabsTrigger>
            <TabsTrigger value="existing">Copy a resume</TabsTrigger>
            <TabsTrigger value="file">From file</TabsTrigger>
            <TabsTrigger value="blank">Blank</TabsTrigger>
          </TabsList>

          <div className="grid gap-4 pt-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor={ids.name} optional={mode === "file"}>
                  Name
                </Label>
                {mode === "file" ? (
                  <p id={ids.nameHint} className="text-muted-foreground text-xs">
                    Defaults to the file name.
                  </p>
                ) : null}
                <Input
                  aria-describedby={mode === "file" ? ids.nameHint : undefined}
                  id={ids.name}
                  value={name}
                  onChange={(e) => {
                    const next = e.target.value;
                    setName(next);
                    if (mode === "existing" && source) {
                      matchName(next);
                    }
                  }}
                />
              </div>
              {mode === "kb" && (
                <div className="grid gap-1.5">
                  <Label htmlFor={ids.role}>Target role</Label>
                  {/* The same searchable picker as the other two tabs — the
                      coarse dropdown here was the one hold-out, reported from
                      live use. The plan endpoint still wants a coarse key;
                      `coarseFromTag` derives it below. */}
                  <RolePicker
                    mode="single"
                    id={ids.role}
                    value={tag}
                    onValueChange={setTag}
                    roleCategories={roleCategories}
                  />
                </div>
              )}
              {(mode === "blank" || mode === "file") && (
                <div className="grid gap-1.5">
                  <Label htmlFor={ids.role} optional>
                    Target role
                  </Label>
                  <RolePicker
                    mode="single"
                    id={ids.role}
                    value={tag}
                    onValueChange={setTag}
                    roleCategories={roleCategories}
                  />
                </div>
              )}
            </div>

            <TabsContent value="kb" className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor={ids.instruction} optional>
                  Focus
                </Label>
                <p id={ids.instructionHint} className="text-muted-foreground text-xs">
                  Guides which items are picked and the tone of the summary.
                  Your bullets are never rewritten.
                </p>
                <Textarea
                  id={ids.instruction}
                  aria-describedby={ids.instructionHint}
                  rows={3}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                />
              </div>

              <div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!tag || proposePlan.isPending}
                  // Stays focusable while it suggests: a disabled button that
                  // has focus drops it to the page.
                  focusableWhenDisabled
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={() => proposeOnce()}
                >
                  {proposePlan.isPending ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <Sparkles aria-hidden />
                  )}
                  {plan ? "Suggest again" : "Suggest items"}
                </Button>
                {!tag && (
                  <span className="text-muted-foreground ml-2 text-xs">
                    Choose a target role first.
                  </span>
                )}
              </div>

              {entities.isLoading ? (
                <p className="text-muted-foreground text-sm">Loading your career history…</p>
              ) : selectable.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Nothing to pick yet. Import a resume into your career history
                  first.
                </p>
              ) : (
                <ul className="max-h-64 divide-y overflow-y-auto rounded-lg border px-3">
                  {selectable.map((entity) => (
                    <li key={entity.id} className="py-2.5">
                      <label className="flex cursor-pointer items-start gap-3">
                        <Checkbox checked={selected.has(entity.id)} onCheckedChange={() => toggle(entity.id)} disabled={busy} className="mt-0.5" />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">
                            {entity.title}
                          </span>
                          <span className="text-muted-foreground block text-xs">
                            {KB_KIND_LABELS[entity.kind]}
                            {entity.org ? ` · ${entity.org}` : ""}
                            {/* A bullet count is only meaningful where the
                                section renders FROM bullets. "0 bullets" on a
                                certification reads as a defect; it is not. */}
                            {rendersWithoutPoints(entity.kind)
                              ? ""
                              : ` · ${approvedCount(entity)} ${approvedCount(entity) === 1 ? "bullet" : "bullets"}`}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}

              {plan && plan.exclude.length > 0 && (
                <div className="grid gap-1">
                  <p className="text-sm font-medium">Not included</p>
                  <ul className="text-muted-foreground space-y-0.5 text-xs">
                    {plan.exclude.map((x) => (
                      <li key={x.id}>
                        <span className="font-medium">{x.title}</span>: {x.reason}
                      </li>
                    ))}
                  </ul>
                  <p className="text-muted-foreground text-xs">
                    Select any above to include it.
                  </p>
                </div>
              )}

              {plan && (
                <div className="grid gap-1.5">
                  <Label htmlFor={ids.summary} optional>
                    Summary
                  </Label>
                  {/* The plan drafts this summary (base_from_kb_plan), so the
                      field arrives filled: the hint asks for a check. It sits
                      between label and field, where it survives typing. */}
                  <p id={ids.summaryHint} className="text-muted-foreground text-xs">
                    Check this summary, or clear it.
                  </p>
                  <Textarea
                    id={ids.summary}
                    aria-describedby={ids.summaryHint}
                    rows={3}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                  />
                </div>
              )}
            </TabsContent>

            <TabsContent value="existing" className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor={ids.source}>Copy from</Label>
                <Select
                  value={source}
                  onValueChange={(v) => selectSource(v as string)}
                >
                  <SelectTrigger id={ids.source} size="sm" className="w-full">
                    <SelectValue placeholder="Choose a resume">
                      {(value) => {
                        const hit = existingResumes.find((r) => r.slug === value);
                        return hit
                          ? baseResumeLabel(hit.slug, [hit])
                          : String(value ?? "");
                      }}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {existingResumes.map((r) => (
                      <SelectItem key={r.slug} value={r.slug}>
                        {baseResumeLabel(r.slug, [r])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-xs">
                  Copies the whole document, including its template and formatting.
                </p>
              </div>

              {source && (
                <div className="grid gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor={ids.copyRole}>Target role</Label>
                    {nameMatchApplied && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={clearNameMatch}
                      >
                        Clear suggestion
                      </Button>
                    )}
                  </div>
                  <RolePicker
                    mode="single"
                    id={ids.copyRole}
                    value={tag}
                    onValueChange={(next) => {
                      setTag(next);
                      setNameMatchApplied(false);
                    }}
                    roleCategories={roleCategories}
                  />
                  <p className="text-muted-foreground text-xs">
                    Copied from the original. Typing a name may suggest a new
                    role.
                  </p>
                </div>
              )}
            </TabsContent>

            <TabsContent value="file" className="grid gap-3">
              <Dropzone
                accept={RESUME_FILE_ACCEPT}
                maxFiles={1}
                maxBytes={IMPORT_MAX_BYTES}
                disabled={busy}
                hint={`${acceptedFilesHint(RESUME_FILE_ACCEPT)} Up to 10 MB.`}
                onFiles={(picked, rejected) => {
                  setFile(picked[0] ?? null);
                  setFileRejected(rejected);
                }}
              />
              {file && (
                <p className="text-sm">
                  <span className="text-muted-foreground">Selected: </span>
                  <span className="font-medium">{file.name}</span>
                </p>
              )}
              {fileRejected.length > 0 && (
                <ul className="space-y-1 text-xs">
                  {fileRejected.map((r) => (
                    <li key={r.file.name} className="text-muted-foreground truncate">
                      <span className="font-medium">{r.file.name}</span>: {r.reason}
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-muted-foreground text-xs">
                We&apos;ll turn the file into a resume you can edit. It won&apos;t be
                added to your career history. You can add it later from the
                resume.
              </p>
            </TabsContent>

            <TabsContent value="blank">
              <p className="text-muted-foreground text-sm">
                An empty document you fill in yourself.
              </p>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter>
          {/* Closing keeps the draft, so the one discard is named for what it
              does. No confirm: the label says what is lost. */}
          {touched && (
            <Button
              variant="ghost"
              className="sm:mr-auto"
              disabled={busy}
              onClick={onStartOver}
            >
              Start over
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Close
          </Button>
          {blocked ? (
            <p id={ids.blocked} className="text-muted-foreground self-center text-xs">
              {blocked}
            </p>
          ) : null}
          <Button
            onClick={() => submit()}
            disabled={!canCreate || busy}
            focusableWhenDisabled
            aria-describedby={blocked ? ids.blocked : undefined}
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
          >
            {busy ? <Loader2 className="animate-spin" /> : null}
            {busy && mode === "file" ? "Reading file…" : "Create"}
          </Button>
        </DialogFooter>
    </>
  );
}
