"use client";

import { useMemo, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  getKbEntity,
  getKbProfile,
  kbPort,
  listKbEntities,
} from "@/lib/api";
import type {
  BaseResumeDetail,
  KBEntityDetail,
  KBEntityKind,
  KBEntitySummary,
  ResumeData,
} from "@/lib/types";

const KINDS: { value: KBEntityKind; label: string }[] = [
  { value: "experience", label: "Experience" },
  { value: "project", label: "Projects" },
  { value: "education", label: "Education" },
  { value: "certification", label: "Certifications" },
];

type EntitySelection = Record<string, string[]>;

export function KbImportDrawer({
  open,
  onOpenChange,
  onImported,
  targetSlug,
  targetData,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (result: BaseResumeDetail) => void;
  targetSlug: string;
  targetData: ResumeData;
}) {
  const queryClient = useQueryClient();
  const [selection, setSelection] = useState<EntitySelection>({});
  const [skillCategories, setSkillCategories] = useState<Set<string>>(new Set());
  const [includeSummary, setIncludeSummary] = useState(false);

  const entities = useQuery({
    queryKey: ["kb", "entities"],
    queryFn: () => listKbEntities(),
    enabled: open,
  });
  const profile = useQuery({
    queryKey: ["kb", "profile"],
    queryFn: getKbProfile,
    enabled: open,
  });
  const visibleEntities = useMemo(
    () => (entities.data ?? []).filter((entity) => entity.status !== "archived"),
    [entities.data],
  );

  const reset = () => {
    setSelection({});
    setSkillCategories(new Set());
    setIncludeSummary(false);
  };
  const handleOpenChange = (next: boolean) => {
    onOpenChange(next);
    if (!next) reset();
  };

  const importMutation = useMutation({
    mutationFn: () =>
      kbPort({
        target_slug: targetSlug,
        items: Object.entries(selection).map(([entityId, pointIds]) => ({
          entity_id: entityId,
          point_ids: pointIds,
        })),
        skill_categories: [...skillCategories],
        include_profile_summary: includeSummary,
      }),
    onSuccess: (response) => {
      const duplicates = response.report.items.reduce(
        (count, item) => count + item.skipped_duplicate_point_ids.length,
        0,
      );
      queryClient.setQueryData(["base-resumes", targetSlug], response.resume);
      void queryClient.invalidateQueries({ queryKey: ["base-resumes"] });
      void queryClient.invalidateQueries({
        queryKey: ["resume-versions", "base", targetSlug],
      });
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      onImported(response.resume);
      toast.success(
        `Imported ${response.report.items.length} ${response.report.items.length === 1 ? "entity" : "entities"} and ${response.report.skills_merged.length} skill ${response.report.skills_merged.length === 1 ? "group" : "groups"}${duplicates ? ` · ${duplicates} duplicate${duplicates === 1 ? "" : "s"} skipped` : ""}`,
      );
      reset();
      onOpenChange(false);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const toggleEntity = (entityId: string, approvedPointIds: string[]) =>
    setSelection((current) => {
      if (Object.hasOwn(current, entityId)) {
        const next = { ...current };
        delete next[entityId];
        return next;
      }
      return { ...current, [entityId]: approvedPointIds };
    });

  const togglePoint = (entityId: string, pointId: string) =>
    setSelection((current) => {
      const points = new Set(current[entityId] ?? []);
      if (points.has(pointId)) points.delete(pointId);
      else points.add(pointId);
      const next = { ...current };
      if (points.size === 0) delete next[entityId];
      else next[entityId] = [...points];
      return next;
    });

  const toggleSkill = (category: string) =>
    setSkillCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });

  const selectedEntityCount = Object.keys(selection).length;
  const selectedPointCount = Object.values(selection).reduce(
    (count, pointIds) => count + pointIds.length,
    0,
  );
  const totalSelections =
    selectedEntityCount + skillCategories.size + (includeSummary ? 1 : 0);

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Import from Career KB</SheetTitle>
          <p className="text-muted-foreground text-sm">
            Choose exact approved points. The import is one versioned operation.
          </p>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-2">
          {entities.isLoading ? (
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading Career KB…
            </p>
          ) : entities.error ? (
            <p role="alert" className="text-destructive text-sm">
              {entities.error.message}
            </p>
          ) : (
            <Tabs defaultValue="experience">
              <TabsList className="flex h-auto flex-wrap">
                {KINDS.map((kind) => (
                  <TabsTrigger key={kind.value} value={kind.value}>
                    {kind.label}
                  </TabsTrigger>
                ))}
                <TabsTrigger value="profile">Profile</TabsTrigger>
              </TabsList>

              {KINDS.map((kind) => {
                const items = visibleEntities.filter((entity) => entity.kind === kind.value);
                return (
                  <TabsContent key={kind.value} value={kind.value}>
                    {items.length === 0 ? (
                      <p className="text-muted-foreground py-6 text-center text-sm">
                        No {kind.label.toLowerCase()} in the Career KB.
                      </p>
                    ) : (
                      <ul className="divide-y">
                        {items.map((entity) => (
                          <EntityPickerRow
                            key={entity.id}
                            open={open}
                            entity={entity}
                            disabled={isAlreadyInResume(entity, targetData)}
                            selectedPointIds={selection[entity.id]}
                            onToggleEntity={toggleEntity}
                            onTogglePoint={togglePoint}
                          />
                        ))}
                      </ul>
                    )}
                  </TabsContent>
                );
              })}

              <TabsContent value="profile" className="space-y-5 py-3">
                {profile.isLoading ? (
                  <p className="text-muted-foreground text-sm">Loading profile…</p>
                ) : profile.error ? (
                  <p role="alert" className="text-destructive text-sm">
                    {profile.error.message}
                  </p>
                ) : (
                  <>
                    <fieldset className="space-y-2">
                      <legend className="text-sm font-semibold">Summary</legend>
                      <label className="flex cursor-pointer items-start gap-3 rounded-lg border p-3">
                        <Checkbox checked={includeSummary} onCheckedChange={() => setIncludeSummary((current) => !current)} disabled={!profile.data?.summary || importMutation.isPending} className="mt-1" />
                        <span className="text-sm leading-relaxed">
                          {profile.data?.summary || "No Career KB summary is available."}
                        </span>
                      </label>
                    </fieldset>
                    <fieldset className="space-y-2">
                      <legend className="text-sm font-semibold">Skill groups</legend>
                      {(profile.data?.skills.length ?? 0) === 0 ? (
                        <p className="text-muted-foreground text-sm">No skill groups.</p>
                      ) : (
                        <div className="space-y-2">
                          {profile.data?.skills.map((group) => {
                            const duplicate = targetData.skills.some(
                              (target) => normalize(target.category) === normalize(group.category),
                            );
                            return (
                              <label
                                key={group.category}
                                className="flex cursor-pointer items-start gap-3 rounded-lg border p-3"
                              >
                                <Checkbox checked={skillCategories.has(group.category)} onCheckedChange={() => toggleSkill(group.category)} disabled={duplicate || importMutation.isPending} className="mt-1" />
                                <span className="min-w-0 flex-1">
                                  <span className="text-sm font-medium">{group.category}</span>
                                  <span className="text-muted-foreground mt-1 block text-xs">
                                    {group.items.join(" · ")}
                                  </span>
                                  {duplicate && (
                                    <Badge variant="secondary" className="mt-2 text-xs">
                                      Already in this resume
                                    </Badge>
                                  )}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      )}
                    </fieldset>
                  </>
                )}
              </TabsContent>
            </Tabs>
          )}
        </div>

        <SheetFooter className="border-t px-4 py-3">
          <div className="text-muted-foreground mr-auto text-xs">
            {selectedEntityCount} entities · {selectedPointCount} points · {skillCategories.size} skill groups
          </div>
          <SheetClose render={<Button variant="ghost">Cancel</Button>} />
          <Button
            disabled={totalSelections === 0 || importMutation.isPending}
            onClick={() => importMutation.mutate()}
          >
            {importMutation.isPending ? "Importing…" : "Import selected"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function EntityPickerRow({
  open,
  entity,
  disabled,
  selectedPointIds,
  onToggleEntity,
  onTogglePoint,
}: {
  open: boolean;
  entity: KBEntitySummary;
  disabled: boolean;
  selectedPointIds: string[] | undefined;
  onToggleEntity: (entityId: string, approvedPointIds: string[]) => void;
  onTogglePoint: (entityId: string, pointId: string) => void;
}) {
  const detail = useQuery({
    queryKey: ["kb", "entity", entity.id],
    queryFn: () => getKbEntity(entity.id),
    enabled: open && !disabled,
  });
  const approved = approvedPoints(detail.data);
  const selected = new Set(selectedPointIds ?? []);
  const entitySelected = selectedPointIds !== undefined;
  const allSelected =
    entitySelected && (approved.length === 0 || selected.size === approved.length);

  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <Checkbox checked={allSelected} onCheckedChange={() => onToggleEntity(entity.id, approved.map((point) => point.id))} disabled={disabled || detail.isLoading || detail.isError} className="mt-1" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">{entity.title}</p>
            <Badge variant="outline" className="capitalize">
              {entity.status}
            </Badge>
            {entity.draft_count > 0 && (
              <Badge variant="secondary">{entity.draft_count} drafts excluded</Badge>
            )}
          </div>
          <p className="text-muted-foreground text-xs">
            {entity.org || "No organization"}
          </p>
          {disabled ? (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Badge variant="secondary" className="mt-2 text-xs">
                    Already in this resume
                  </Badge>
                }
              />
              <TooltipContent>
                A matching structured entry already exists in the target resume.
              </TooltipContent>
            </Tooltip>
          ) : detail.isLoading ? (
            <p className="text-muted-foreground mt-2 text-xs">Loading approved points…</p>
          ) : detail.error ? (
            <p role="alert" className="text-destructive mt-2 text-xs">
              {detail.error.message}
            </p>
          ) : approved.length === 0 ? (
            <p className="text-muted-foreground mt-2 text-xs">
              Structured entry only, no approved points.
            </p>
          ) : (
            <div className="mt-3 space-y-2 border-l pl-3">
              {approved.map((point) => (
                <label key={point.id} className="flex cursor-pointer items-start gap-2 text-xs">
                  <Checkbox checked={selected.has(point.id)} onCheckedChange={() => onTogglePoint(entity.id, point.id)} className="mt-0.5" />
                  <span className="leading-relaxed">{point.text}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function approvedPoints(detail: KBEntityDetail | undefined) {
  return detail?.points.filter((point) => point.state === "approved") ?? [];
}

function normalize(value: string | null | undefined) {
  return (value ?? "").trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

function isAlreadyInResume(entity: KBEntitySummary, target: ResumeData): boolean {
  if (entity.kind === "experience") {
    return target.experience.some(
      (entry) =>
        normalize(entry.company) === normalize(entity.org) &&
        normalize(entry.role) === normalize(entity.title) &&
        (entry.start_date || "") === (entity.start_date || ""),
    );
  }
  if (entity.kind === "project") {
    return target.projects.some((entry) => normalize(entry.name) === normalize(entity.title));
  }
  if (entity.kind === "education") {
    return target.education.some(
      (entry) =>
        normalize(entry.institution) === normalize(entity.org) &&
        normalize(entry.degree) === normalize(entity.title),
    );
  }
  const certification = entity.org ? `${entity.title} (${entity.org})` : entity.title;
  return target.certifications.some((entry) => normalize(entry) === normalize(certification));
}
