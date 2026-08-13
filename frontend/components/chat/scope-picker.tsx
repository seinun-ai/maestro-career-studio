"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BriefcaseBusiness, ChevronDown, ChevronRight, Plus, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { listKbEntities } from "@/lib/api";
import type { ChatSelection, ResumeData } from "@/lib/types";

function selectionKey(s: ChatSelection): string {
  if (s.kind === "kb_entity") return `kb:${s.entity_id}`;
  return `${s.section}:${s.index ?? ""}:${s.bullet_index ?? ""}`;
}

/** Removable pill showing one referenced item (Cursor-style atomic chip). */
export function SelectionChip({
  selection,
  onRemove,
}: {
  selection: ChatSelection;
  onRemove?: () => void;
}) {
  return (
    <Badge variant="secondary" className="gap-1 font-normal">
      {selection.kind === "kb_entity" && (
        <BriefcaseBusiness className="size-3" aria-hidden="true" />
      )}
      <span className="max-w-48 truncate">
        {selection.label ??
          (selection.kind === "kb_entity"
            ? "KB entity"
            : `${selection.section ?? "?"}${selection.index != null ? `[${selection.index}]` : ""}`)}
      </span>
      {onRemove && (
        <button
          type="button"
          aria-label="Remove scope"
          className="hover:text-destructive"
          onClick={onRemove}
        >
          <X className="size-3" />
        </button>
      )}
    </Badge>
  );
}

interface SectionSpec {
  section: string;
  title: string;
  items: { label: string; bullets: string[] }[];
}

function buildSections(data: ResumeData): SectionSpec[] {
  const specs: SectionSpec[] = [
    { section: "summary", title: "Summary", items: [] },
    { section: "contact", title: "Contact", items: [] },
    {
      section: "skills",
      title: "Skills",
      items: data.skills.map((g) => ({ label: g.category, bullets: [] })),
    },
    {
      section: "experience",
      title: "Experience",
      items: data.experience.map((e) => ({
        label: `${e.company} — ${e.role}`,
        bullets: e.bullets,
      })),
    },
    {
      section: "projects",
      title: "Projects",
      items: data.projects.map((p) => ({ label: p.name, bullets: p.bullets })),
    },
    {
      section: "education",
      title: "Education",
      items: data.education.map((e) => ({
        label: e.degree ? `${e.institution} — ${e.degree}` : e.institution,
        bullets: e.bullets,
      })),
    },
    { section: "certifications", title: "Certifications", items: [] },
  ];

  // Custom sections scope on their stable `key` (the `section_key`), never a
  // fragile `extra_sections[i]` index. Entry-style sections expose per-entry and
  // per-bullet paths; bullet-style sections are whole-section only (like Skills).
  for (const extra of data.extra_sections ?? []) {
    specs.push({
      section: extra.key,
      title: extra.title,
      items:
        extra.type === "entries"
          ? extra.entries.map((e) => ({
              label: e.heading || "Untitled entry",
              bullets: e.bullets,
            }))
          : [],
    });
  }

  return specs;
}

/**
 * Structured select-then-ask: resume sections → items → bullets from the
 * pinned resume, plus Career KB entities, become reference chips. Skills
 * items are group-level only (the backend guards skills ops at section
 * granularity). Resume chips scope edits; KB chips pin context.
 */
export function ScopePickerDialog({
  open,
  onOpenChange,
  data,
  resumeState = "none",
  selections,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data?: ResumeData;
  /** Pinned-resume fetch state: distinguishes "nothing pinned" from loading/error. */
  resumeState?: "none" | "loading" | "error" | "ready";
  selections: ChatSelection[];
  onAdd: (selection: ChatSelection) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const existing = new Set(selections.map(selectionKey));

  const kbEntities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => listKbEntities(),
    enabled: open,
  });

  const add = (selection: ChatSelection) => {
    if (!existing.has(selectionKey(selection))) onAdd(selection);
  };

  const toggleExpand = (key: string) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Fixed header + dedicated scroll body: tall resumes must scroll inside
          the dialog, never push it past the viewport. */}
      <DialogContent className="flex max-h-[80vh] w-[min(92vw,34rem)] max-w-[min(92vw,34rem)] flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>Add context</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground -mt-2 text-xs">
          Resume chips limit what can be edited. Career KB chips add
          background the assistant reads first.
        </p>
        <Tabs defaultValue="resume" className="flex min-h-0 flex-1 flex-col gap-3">
          <TabsList className="w-fit rounded-full bg-muted/70 p-1">
            <TabsTrigger value="resume">Resume</TabsTrigger>
            <TabsTrigger value="kb">Career KB</TabsTrigger>
          </TabsList>

          <TabsContent value="kb" className="min-h-0 flex-1 overflow-y-auto pr-1">
            {kbEntities.isLoading ? (
              <p className="text-muted-foreground text-sm">Loading Career KB…</p>
            ) : kbEntities.error ? (
              <p role="alert" className="text-destructive text-sm">
                {(kbEntities.error as Error).message}
              </p>
            ) : (kbEntities.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No Career KB entities yet.
              </p>
            ) : (
              <ul className="space-y-1">
                {(kbEntities.data ?? []).map((entity) => (
                  <li
                    key={entity.id}
                    className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm">{entity.title}</p>
                      <p className="text-muted-foreground text-xs capitalize">
                        {entity.kind}
                        {entity.org ? ` · ${entity.org}` : ""}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Pin ${entity.title}`}
                      onClick={() =>
                        add({
                          kind: "kb_entity",
                          entity_id: entity.id,
                          label: entity.title,
                        })
                      }
                    >
                      <Plus className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>

          <TabsContent
            value="resume"
            className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1"
          >
            {!data ? (
              <p
                className={
                  resumeState === "error"
                    ? "text-destructive text-sm"
                    : "text-muted-foreground text-sm"
                }
                role={resumeState === "error" ? "alert" : undefined}
              >
                {resumeState === "loading"
                  ? "Loading the pinned resume…"
                  : resumeState === "error"
                    ? "Couldn't load the pinned resume."
                    : "Pin a resume in the composer to scope its sections."}
              </p>
            ) : (
              buildSections(data).map((spec) => (
            <div key={spec.section}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{spec.title}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    add({ section: spec.section, label: spec.title })
                  }
                >
                  <Plus className="mr-1 size-3" /> whole section
                </Button>
              </div>
              {spec.items.length > 0 && (
                <ul className="mt-1 space-y-1">
                  {spec.items.map((item, index) => {
                    // Skills chips stay group-level: section-only scope.
                    const itemSelection: ChatSelection =
                      spec.section === "skills"
                        ? { section: "skills", label: `Skills · ${item.label}` }
                        : {
                            section: spec.section,
                            index,
                            label: `${spec.title} · ${item.label}`,
                          };
                    const expandKey = `${spec.section}:${index}`;
                    return (
                      <li key={index} className="rounded-md border px-2 py-1">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1">
                            {item.bullets.length > 0 ? (
                              <button
                                type="button"
                                aria-label="Show bullets"
                                onClick={() => toggleExpand(expandKey)}
                                className="text-muted-foreground shrink-0"
                              >
                                {expanded.has(expandKey) ? (
                                  <ChevronDown className="size-3.5" />
                                ) : (
                                  <ChevronRight className="size-3.5" />
                                )}
                              </button>
                            ) : (
                              <span className="w-3.5 shrink-0" />
                            )}
                            <span className="truncate text-sm">{item.label}</span>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Add ${item.label} to scope`}
                            onClick={() => add(itemSelection)}
                          >
                            <Plus className="size-3.5" />
                          </Button>
                        </div>
                        {expanded.has(expandKey) && (
                          <ul className="mt-1 ml-5 space-y-1">
                            {item.bullets.map((bullet, bulletIndex) => (
                              <li
                                key={bulletIndex}
                                className="flex items-start justify-between gap-2"
                              >
                                <span className="text-muted-foreground line-clamp-2 text-xs">
                                  {bullet}
                                </span>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label="Add bullet to scope"
                                  className="shrink-0"
                                  onClick={() =>
                                    add({
                                      section: spec.section,
                                      index,
                                      bullet_index: bulletIndex,
                                      label: `${item.label} · bullet ${bulletIndex + 1}`,
                                    })
                                  }
                                >
                                  <Plus className="size-3" />
                                </Button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
              ))
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
