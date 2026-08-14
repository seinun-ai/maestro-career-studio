"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

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
import { createKbEntity } from "@/lib/api";
import {
  SECTION_PRESETS,
  TITLE_COLLISION_MESSAGE,
  isCoreSectionTitle,
  slugifyKey,
} from "@/lib/extra-sections";
import type { KBEntityKind, KBEntityStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const KINDS: { value: KBEntityKind; label: string }[] = [
  { value: "experience", label: "Experience" },
  { value: "project", label: "Project" },
  { value: "education", label: "Education" },
  { value: "certification", label: "Certification" },
  { value: "extra", label: "Custom section" },
];

const STATUSES: { value: KBEntityStatus; label: string }[] = [
  { value: "ongoing", label: "Ongoing" },
  { value: "completed", label: "Completed" },
  { value: "archived", label: "Archived" },
];

export function NewEntityDialog({
  open,
  onOpenChange,
  defaultKind = "experience",
  defaultSectionKey,
  defaultSectionTitle,
  defaultSectionType = "entries",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultKind?: KBEntityKind;
  defaultSectionKey?: string;
  defaultSectionTitle?: string;
  defaultSectionType?: "entries" | "bullets";
}) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<KBEntityKind>(defaultKind);
  const [title, setTitle] = useState("");
  const [org, setOrg] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState<KBEntityStatus>("ongoing");

  // Custom section fields
  const [sectionTitle, setSectionTitle] = useState(defaultSectionTitle ?? "");
  const [sectionKey, setSectionKey] = useState(defaultSectionKey ?? "");
  const [sectionType, setSectionType] = useState<"entries" | "bullets">(defaultSectionType);

  const reset = () => {
    setKind(defaultKind);
    setTitle("");
    setOrg("");
    setStartDate("");
    setEndDate("");
    setStatus("ongoing");
    setSectionTitle(defaultSectionTitle ?? "");
    setSectionKey(defaultSectionKey ?? "");
    setSectionType(defaultSectionType);
  };

  const titleCollides = kind === "extra" && isCoreSectionTitle(sectionTitle);

  const create = useMutation({
    mutationFn: () => {
      if (kind === "extra") {
        const sTitle = sectionTitle.trim();
        const sKey = (sectionKey.trim() || slugifyKey(sTitle)) || "custom-section";
        const eTitle = sectionType === "bullets" ? sTitle : title.trim();
        return createKbEntity({
          kind: "extra",
          title: eTitle,
          org: sectionType === "bullets" ? null : org.trim() || null,
          start_date: startDate.trim() || null,
          end_date: endDate.trim() || null,
          status: sectionType === "bullets" ? "completed" : status,
          section_key: sKey,
          section_type: sectionType,
          section_title: sTitle,
          detail: {
            section_key: sKey,
            section_type: sectionType,
            section_title: sTitle,
          },
        });
      }
      return createKbEntity({
        kind,
        title: title.trim(),
        org: org.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        status,
      });
    },
    onSuccess: (entity) => {
      toast.success(`${entity.title} added to Career KB`);
      void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
      onOpenChange(false);
      reset();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const isValid =
    kind === "extra"
      ? sectionTitle.trim() &&
        !titleCollides &&
        (sectionType === "bullets" || title.trim())
      : title.trim();

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isValid) create.mutate();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next && !create.isPending) reset();
      }}
    >
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>New career item</DialogTitle>
          <DialogDescription>
            Add a career record manually.
          </DialogDescription>
        </DialogHeader>
        <form id="new-career-entity" className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-1.5">
            <Label htmlFor="career-entity-kind">Category</Label>
            <Select
              value={kind}
              onValueChange={(value) =>
                value && setKind(value as KBEntityKind)
              }
              disabled={create.isPending}
            >
              <SelectTrigger id="career-entity-kind" className="w-full">
                <SelectValue>{KINDS.find((item) => item.value === kind)?.label}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {kind === "extra" && (
            <div className="space-y-4 rounded-xl border p-3.5 bg-muted/20">
              <div className="grid gap-1.5">
                <Label>Section Presets</Label>
                <div className="flex flex-wrap gap-1.5">
                  {SECTION_PRESETS.map((preset) => (
                    <Button
                      key={preset.id}
                      type="button"
                      variant={sectionTitle === preset.title ? "default" : "outline"}
                      size="sm"
                      className="text-xs"
                      onClick={() => {
                        setSectionTitle(preset.title);
                        setSectionKey(preset.id);
                        setSectionType(preset.type);
                        if (preset.type === "bullets") {
                          setTitle(preset.title);
                        }
                      }}
                    >
                      {preset.label}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="career-section-name">Section Name</Label>
                <Input
                  id="career-section-name"
                  value={sectionTitle}
                  onChange={(e) => {
                    setSectionTitle(e.target.value);
                    if (!sectionKey || sectionKey === slugifyKey(sectionTitle)) {
                      setSectionKey(slugifyKey(e.target.value));
                    }
                  }}
                  placeholder="e.g. Publications, Volunteer Work"
                  required
                  aria-invalid={titleCollides}
                  disabled={create.isPending}
                />
                {titleCollides && (
                  <span className="text-destructive text-xs">
                    {TITLE_COLLISION_MESSAGE}
                  </span>
                )}
              </div>

              <div className="grid gap-1.5">
                <Label>Section Type</Label>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setSectionType("entries")}
                    className={cn(
                      "flex flex-1 flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left transition-colors",
                      sectionType === "entries"
                        ? "border-primary bg-primary/5 font-medium"
                        : "border-input hover:border-border text-muted-foreground",
                    )}
                  >
                    <span className="text-xs font-semibold text-foreground">Entries</span>
                    <span className="text-[11px] text-muted-foreground">Titled items with heading & details</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSectionType("bullets");
                      if (sectionTitle.trim()) {
                        setTitle(sectionTitle.trim());
                      }
                    }}
                    className={cn(
                      "flex flex-1 flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left transition-colors",
                      sectionType === "bullets"
                        ? "border-primary bg-primary/5 font-medium"
                        : "border-input hover:border-border text-muted-foreground",
                    )}
                  >
                    <span className="text-xs font-semibold text-foreground">Bullets</span>
                    <span className="text-[11px] text-muted-foreground">Simple list of bullet points</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {kind !== "extra" || sectionType === "entries" ? (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="career-entity-title">
                  {kind === "extra" ? "Entry Heading" : kind === "project" ? "Project Name" : "Title / Role"}
                </Label>
                <Input
                  id="career-entity-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={
                    kind === "extra"
                      ? "e.g. Paper Title or Role"
                      : kind === "project"
                        ? "Project name"
                        : "Role or title"
                  }
                  autoFocus
                  required
                  disabled={create.isPending}
                />
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="career-entity-org">
                  {kind === "extra" ? "Subheading / Issuer" : "Organization"}{" "}
                  <span className="text-muted-foreground">· optional</span>
                </Label>
                <Input
                  id="career-entity-org"
                  value={org}
                  onChange={(event) => setOrg(event.target.value)}
                  placeholder={
                    kind === "extra"
                      ? "Conference, publisher, or org"
                      : "Company, institution, or issuer"
                  }
                  disabled={create.isPending}
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="career-entity-start">
                    Start date <span className="text-muted-foreground">· optional</span>
                  </Label>
                  <Input
                    id="career-entity-start"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                    placeholder="Jan 2025"
                    disabled={create.isPending}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="career-entity-end">
                    End date <span className="text-muted-foreground">· optional</span>
                  </Label>
                  <Input
                    id="career-entity-end"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                    placeholder="Present"
                    disabled={create.isPending}
                  />
                </div>
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="career-entity-status">Status</Label>
                <Select
                  value={status}
                  onValueChange={(value) =>
                    value && setStatus(value as KBEntityStatus)
                  }
                  disabled={create.isPending}
                >
                  <SelectTrigger id="career-entity-status" className="w-full">
                    <SelectValue>{STATUSES.find((item) => item.value === status)?.label}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              Creating this bullet-list section entity in the Knowledge Base. You can add and approve bullet points on it after creation.
            </p>
          )}
        </form>
        <DialogFooter>
          <Button
            variant="outline"
            type="button"
            className="rounded-full"
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
            disabled={create.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="new-career-entity"
            className="rounded-full px-4"
            disabled={!isValid || create.isPending}
          >
            {create.isPending ? "Adding…" : "Add career item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
