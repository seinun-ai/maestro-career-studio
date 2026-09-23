"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useSingleFlight } from "@/hooks/use-single-flight";
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
  landOn,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultKind?: KBEntityKind;
  defaultSectionKey?: string;
  defaultSectionTitle?: string;
  defaultSectionType?: "entries" | "bullets";
  /** The new item's element once the list shows it, for focus after a create. */
  landOn?: (id: string) => HTMLElement | null;
}) {
  const queryClient = useQueryClient();
  const presetsLabelId = useId();
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

  // Closing keeps the draft (Esc, the overlay, Close); only a create clears
  // it. Each open hands an untouched form the opener's kind (the tab it was
  // opened from), while typed text keeps the kind it was typed for.
  const pristine =
    !title.trim() &&
    !org.trim() &&
    !startDate.trim() &&
    !endDate.trim() &&
    sectionTitle === (defaultSectionTitle ?? "") &&
    sectionKey === (defaultSectionKey ?? "");
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open && pristine) setKind(defaultKind);
  }

  // Focus never falls to <body>. Initial focus is Base UI's `initialFocus`:
  // an `autoFocus` title took focus before Base UI recorded the opener, so
  // every close returned to the unmounted title. A create returns to the new
  // item instead. Text fields go read-only, not disabled, while a create
  // runs: Enter submits from one, and a disabled field drops its focus.
  const titleRef = useRef<HTMLInputElement>(null);
  const created = useRef<string | null>(null);

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
    onSuccess: async (entity) => {
      toast.success(`${entity.title} added to Career KB`);
      // Close once the list holds the new card, so focus can land on it.
      created.current = entity.id;
      await queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });
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

  const createOnce = useSingleFlight(create.mutate);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isValid) createOnce();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="sm"
        initialFocus={titleRef}
        finalFocus={() => {
          const id = created.current;
          created.current = null;
          return (id ? landOn?.(id) : null) ?? true;
        }}
      >
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
                <Label id={presetsLabelId}>Section presets</Label>
                <div role="group" aria-labelledby={presetsLabelId} className="flex flex-wrap gap-1.5">
                  {SECTION_PRESETS.map((preset) => {
                    const on = sectionTitle === preset.title;
                    return (
                      <Button
                        key={preset.id}
                        type="button"
                        size="sm"
                        className="text-xs"
                        variant={on ? "tonal" : "outline"} aria-pressed={on}
                        onClick={() => {
                          setSectionTitle(preset.title);
                          setSectionKey(preset.id);
                          setSectionType(preset.type);
                          if (preset.type === "bullets") {
                            setTitle(preset.title);
                          }
                        }}
                      >
                        {on && <Check />}
                        {preset.label}
                      </Button>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="career-section-name">Section name</Label>
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
                  readOnly={create.isPending}
                />
                {titleCollides && (
                  <span className="text-destructive text-xs">
                    {TITLE_COLLISION_MESSAGE}
                  </span>
                )}
              </div>

              <div className="grid gap-1.5">
                <Label>Section type</Label>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    aria-pressed={sectionType === "entries"}
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
                    aria-pressed={sectionType === "bullets"}
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
                      ? "e.g. Best Paper Award"
                      : kind === "project"
                        ? "e.g. Fraud detection pipeline"
                        : kind === "education"
                          ? "e.g. MSc Computer Science"
                          : kind === "certification"
                            ? "e.g. AWS Solutions Architect"
                            : "e.g. Senior Data Scientist"
                  }
                  ref={titleRef}
                  required
                  readOnly={create.isPending}
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
                      ? "e.g. NeurIPS 2024"
                      : kind === "education"
                        ? "e.g. University of Toronto"
                        : kind === "certification"
                          ? "e.g. Amazon Web Services"
                          : "e.g. Acme Corp"
                  }
                  readOnly={create.isPending}
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
                    placeholder="e.g. Jan 2025"
                    readOnly={create.isPending}
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
                    placeholder="e.g. Mar 2025"
                    readOnly={create.isPending}
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
            onClick={() => onOpenChange(false)}
            disabled={create.isPending}
          >
            Close
          </Button>
          <Button
            type="submit"
            form="new-career-entity"
            // Focusable while it adds: a disabled button drops focus.
            className="rounded-full px-4 data-disabled:pointer-events-none data-disabled:opacity-50"
            disabled={!isValid || create.isPending}
            focusableWhenDisabled
          >
            {create.isPending ? "Adding…" : "Add career item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
