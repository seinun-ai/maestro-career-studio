"use client";

import { useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

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
import { uniqueSlug } from "@/lib/slug";
import type {
  BaseResumeDetail,
  BaseResumeSummary,
  FavoredRole,
  KBEntitySummary,
  RoleMatch,
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

const KIND_LABELS: Record<KBEntitySummary["kind"], string> = {
  experience: "Experience",
  project: "Project",
  education: "Education",
  certification: "Certification",
};

type Plan = {
  include: string[];
  exclude: { id: string; title: string; reason: string }[];
  summary: string;
};

type Mode = "kb" | "existing" | "blank";

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
  /** Pre-select a target role, e.g. from a suggested-base prompt. */
  initialRole?: string;
  existingResumes: BaseResumeSummary[];
}) {
  // Lifted only so a backdrop/Esc close cannot yank the dialog mid-create.
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>New base resume</DialogTitle>
          <DialogDescription>
            Build it from your Career Knowledge Base, copy one you already have,
            or start from an empty document.
          </DialogDescription>
        </DialogHeader>
        {/* Remount per open: field state resets by construction, with no
            reset-in-an-effect to keep in sync. */}
        <NewBaseResumeForm
          key={open ? "open" : "closed"}
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
  onOpenChange,
  onBusyChange,
  initialMode,
  initialRole,
  existingResumes,
}: {
  onOpenChange: (open: boolean) => void;
  onBusyChange: (busy: boolean) => void;
  initialMode: Mode;
  initialRole?: string;
  existingResumes: BaseResumeSummary[];
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const roles = useRoleCategories();

  const [mode, setMode] = useState<Mode>(initialMode);
  const [name, setName] = useState("");
  // ALL three tabs share the free-text tag picker now. The KB tab's plan
  // endpoint still wants a coarse key, derived on demand by coarseFromTag —
  // one picker state, not a parallel kbRole that could disagree with it.
  const [tag, setTag] = useState<FavoredRole | null>(() =>
    initialRole
      ? favoredRoleFromTag(initialRole, null, undefined)
      : null,
  );
  const [nameMatchApplied, setNameMatchApplied] = useState(false);
  const pendingNameMatch = useRef<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [source, setSource] = useState("");
  const slugsTaken = existingResumes.map((r) => r.slug);

  // The coarse key a FavoredRole implies, for the two KB calls that need one.
  // A confirmed mapping wins; a catalog pick resolves through the catalog (a
  // coarse key is itself, a specific role finds its parent group); unmapped
  // free text is `other` — the projection the server would store anyway.
  const coarseFromTag = (entry: FavoredRole | null): string => {
    if (!entry) return "";
    if (entry.category) return entry.category;
    if (entry.role) {
      const parent = (roles.data ?? []).find(
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
    enabled: mode === "kb",
  });
  // Experience and projects render FROM their bullets, so one with no approved
  // points would be an empty entry. Certifications render as a bare title and
  // education from institution/degree/dates, so those are fine at zero.
  const selectable = (entities.data ?? []).filter(
    (e) =>
      e.status !== "archived" &&
      (e.point_count > 0 || rendersWithoutPoints(e.kind)),
  );

  const done = (created: BaseResumeDetail) => {
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["setup-status"] });
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
        toast.warning("Nothing was selected. Pick entries yourself below.");
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

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
        return apiFetch<BaseResumeDetail>(
          `/api/base-resumes/${created.slug}/identity`,
          {
            method: "PATCH",
            body: JSON.stringify(body),
          },
        );
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
    onError: (err: Error) => toast.error(err.message),
    onSettled: () => onBusyChange(false),
  });

  const busy = create.isPending;

  const canCreate =
    mode === "kb"
      ? Boolean(tag) && selected.size > 0
      : mode === "existing"
        ? Boolean(source)
        : Boolean(name.trim());

  const submit = () => create.mutate();

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
            <TabsTrigger value="kb">From Career KB</TabsTrigger>
            <TabsTrigger value="existing">From existing</TabsTrigger>
            <TabsTrigger value="blank">Blank</TabsTrigger>
          </TabsList>

          <div className="grid gap-4 pt-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="nbr_name">Name</Label>
                <Input
                  id="nbr_name"
                  placeholder="Machine Learning Engineer"
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
                  <Label htmlFor="nbr_role">Target role</Label>
                  {/* The same searchable picker as the other two tabs — the
                      coarse dropdown here was the one hold-out, reported from
                      live use. The plan endpoint still wants a coarse key;
                      `coarseFromTag` derives it below. */}
                  <RolePicker
                    mode="single"
                    id="nbr_role"
                    value={tag}
                    onValueChange={setTag}
                    roleCategories={roles.data}
                  />
                </div>
              )}
              {mode === "blank" && (
                <div className="grid gap-1.5">
                  <Label htmlFor="nbr_role">
                    Target role
                    <span className="text-muted-foreground"> (optional)</span>
                  </Label>
                  <RolePicker
                    mode="single"
                    id="nbr_role"
                    value={tag}
                    onValueChange={setTag}
                    roleCategories={roles.data}
                  />
                </div>
              )}
            </div>

            <TabsContent value="kb" className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor="nbr_instruction" optional>
                  How should this resume be shaped?
                </Label>
                <p id="nbr_instruction_hint" className="text-muted-foreground text-xs">
                  Steers which entries are picked and the tone of the summary.
                  Your bullets are used exactly as written.
                </p>
                <Textarea
                  id="nbr_instruction"
                  aria-describedby="nbr_instruction_hint"
                  rows={3}
                  placeholder="e.g. Lead with production ML work, senior in tone"
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
                  onClick={() => proposePlan.mutate()}
                >
                  {proposePlan.isPending ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <Sparkles aria-hidden />
                  )}
                  {plan ? "Suggest again" : "Suggest a selection"}
                </Button>
                {!tag && (
                  <span className="text-muted-foreground ml-2 text-xs">
                    Choose a target role first.
                  </span>
                )}
              </div>

              {entities.isLoading ? (
                <p className="text-muted-foreground text-sm">Loading Career KB…</p>
              ) : selectable.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Your Career KB has no entries with approved points yet. Import
                  a resume first.
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
                            {KIND_LABELS[entity.kind]}
                            {entity.org ? ` · ${entity.org}` : ""}
                            {/* A bullet count is only meaningful where the
                                section renders FROM bullets. "0 points" on a
                                certification reads as a defect; it is not. */}
                            {rendersWithoutPoints(entity.kind)
                              ? ""
                              : ` · ${entity.point_count} point${entity.point_count === 1 ? "" : "s"}`}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}

              {plan && plan.exclude.length > 0 && (
                <div className="grid gap-1">
                  <p className="text-sm font-medium">Left off</p>
                  <ul className="text-muted-foreground space-y-0.5 text-xs">
                    {plan.exclude.map((x) => (
                      <li key={x.id}>
                        <span className="font-medium">{x.title}</span> — {x.reason}
                      </li>
                    ))}
                  </ul>
                  <p className="text-muted-foreground text-xs">
                    Tick any of these above to put them back on.
                  </p>
                </div>
              )}

              {plan && (
                <div className="grid gap-1.5">
                  <Label htmlFor="nbr_summary" optional>
                    Summary
                  </Label>
                  {/* This was a placeholder, which is the wrong place for a
                      statement about the field: it vanishes as soon as you
                      type, so the reasoning disappears exactly when you act
                      on it. */}
                  <p id="nbr_summary_hint" className="text-muted-foreground text-xs">
                    Left blank on purpose. A wrong summary is worse than none.
                  </p>
                  <Textarea
                    id="nbr_summary"
                    aria-describedby="nbr_summary_hint"
                    rows={3}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                  />
                </div>
              )}
            </TabsContent>

            <TabsContent value="existing" className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor="nbr_source">Copy from</Label>
                <Select
                  value={source}
                  onValueChange={(v) => selectSource(v as string)}
                >
                  <SelectTrigger id="nbr_source" size="sm" className="w-full">
                    <SelectValue placeholder="Choose a base resume">
                      {(value) => {
                        const hit = existingResumes.find((r) => r.slug === value);
                        return hit
                          ? (hit.display_name ?? hit.slug)
                          : String(value ?? "");
                      }}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {existingResumes.map((r) => (
                      <SelectItem key={r.slug} value={r.slug}>
                        {r.display_name ?? r.slug}
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
                    <Label htmlFor="nbr_copy_role">Target role</Label>
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
                    id="nbr_copy_role"
                    value={tag}
                    onValueChange={(next) => {
                      setTag(next);
                      setNameMatchApplied(false);
                    }}
                    roleCategories={roles.data}
                  />
                  <p className="text-muted-foreground text-xs">
                    Starts as the source resume&apos;s tag. Typing a Name that
                    matches the catalog pre-fills a suggestion you can clear.
                  </p>
                </div>
              )}
            </TabsContent>

            <TabsContent value="blank">
              <p className="text-muted-foreground text-sm">
                An empty document you fill in yourself.
              </p>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canCreate || busy}>
            {busy ? <Loader2 className="animate-spin" /> : null}
            Create
          </Button>
        </DialogFooter>
    </>
  );
}
