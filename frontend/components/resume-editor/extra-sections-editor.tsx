"use client";

import { useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  Eye,
  EyeOff,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";

import { useConfirm } from "@/components/confirm-dialog";
import { BulletList } from "@/components/resume-editor/bullet-list";
import { EditableCard } from "@/components/resume-editor/editable-card";
import {
  AddEntryButton,
  cardReorderProps,
  useEntryEditing,
  createEnableAction,
  BulletsRead,
  HiddenBadge,
} from "@/components/resume-editor/editor-scaffold";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import {
  SECTION_PRESETS,
  SECTION_TYPE_LABELS,
  TITLE_COLLISION_MESSAGE,
  emptyEntry,
  isCoreSectionTitle,
  isEnabled,
  newSection,
} from "@/lib/extra-sections";
import { Field } from "@/components/resume-editor/field";
import type {
  ExtraSection,
  ExtraSectionEntry,
  ExtraSectionType,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Shared editor for `ResumeData.extra_sections`, used by BOTH the base-resume
 * editor and the application studio (design: "one shared ResumeSectionsEditor …
 * do not add a seventh duplicated tab to each file"). Sections are identified by
 * their stable `key`; renaming edits `title` only and never touches `key`.
 * Enabled custom content contributes undated ATS evidence; dates in custom
 * sections are display metadata, not employment recency.
 */
export function ExtraSectionsEditor({
  value,
  onChange,
}: {
  value: ExtraSection[];
  onChange: (next: ExtraSection[]) => void;
}) {
  const [addOpen, setAddOpen] = useState(false);

  const replaceAt = (i: number, next: ExtraSection) =>
    onChange(value.map((s, idx) => (idx === i ? next : s)));

  const existingKeys = value.map((s) => s.key);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground text-xs">
        Dates here don&apos;t count as work history.
      </p>

      {value.length === 0 ? (
        <p className="text-muted-foreground rounded-md border border-dashed px-3 py-6 text-center text-sm italic">
          No other sections yet.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {value.map((section, i) => (
            <SectionCard
              key={section.key}
              section={section}
              onChange={(next) => replaceAt(i, next)}
              {...cardReorderProps(value, i, onChange)}
            />
          ))}
        </div>
      )}

      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground hover:text-foreground self-start"
        onClick={() => setAddOpen(true)}
      >
        <Plus className="size-3.5" /> Add section
      </Button>

      <AddSectionDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        existingKeys={existingKeys}
        onAdd={(section) => {
          onChange([...value, section]);
          setAddOpen(false);
        }}
      />
    </div>
  );
}

function SectionCard({
  section,
  onChange,
  onMoveUp,
  onMoveDown,
  onDelete,
}: {
  section: ExtraSection;
  onChange: (next: ExtraSection) => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDelete: () => void;
}) {
  const confirm = useConfirm();
  const [renaming, setRenaming] = useState(false);
  const enabled = isEnabled(section);
  // Title captured when rename begins, restored if the user leaves a name that
  // would collide with a core section header (which the schema also rejects).
  const renameOriginalRef = useRef(section.title);
  const titleCollides = renaming && isCoreSectionTitle(section.title);
  // Names the move and delete buttons, which repeat on every section card.
  const sectionName = section.title.trim() || "this section";
  // Enter, Escape and Done (and a blur the save shortcut forced) unmount the
  // name input: focus moves to the rename button. Not after a blur INTO
  // something (a click, Tab): that is where the user put focus.
  const renameButtonRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();

  const startRename = () => {
    renameOriginalRef.current = section.title;
    setRenaming(true);
  };
  const commitRename = (refocus = true) => {
    // Never commit an empty title (schema contract) or one that duplicates a
    // core section header — deny it here so Save can't fail on it later.
    if (!section.title.trim()) {
      onChange({ ...section, title: "Untitled section" });
    } else if (isCoreSectionTitle(section.title)) {
      onChange({ ...section, title: renameOriginalRef.current });
    }
    setRenaming(false);
    if (refocus) focusNext(renameButtonRef);
  };

  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        !enabled && "bg-muted/20 opacity-70",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 items-center gap-2">
            {renaming ? (
              <Input
                aria-label="Section name"
                autoFocus
                aria-invalid={titleCollides}
                value={section.title}
                onChange={(e) => onChange({ ...section, title: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    onChange({ ...section, title: renameOriginalRef.current });
                    setRenaming(false);
                    focusNext(renameButtonRef);
                  } else if (e.key === "Enter" && !titleCollides) {
                    // Focus moves to the rename button in this same event:
                    // left alone, Enter's activation then pressed it and
                    // reopened the rename.
                    e.preventDefault();
                    commitRename();
                  }
                }}
                onBlur={(e) => commitRename(e.relatedTarget === null)}
                className="h-7 w-56"
              />
            ) : (
              <span className="truncate text-sm font-semibold">
                {section.title || (
                  <em className="opacity-60">Untitled section</em>
                )}
              </span>
            )}
            <Badge variant="secondary" className="shrink-0 text-xs font-normal">
              {SECTION_TYPE_LABELS[section.type]}
            </Badge>
            {!enabled && (
              <Badge variant="outline" className="shrink-0 text-xs">
                Hidden
              </Badge>
            )}
          </div>
          {titleCollides && (
            <span className="text-destructive text-xs">
              {TITLE_COLLISION_MESSAGE}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <label className="text-muted-foreground mr-1 flex items-center gap-1.5 text-xs">
            {enabled ? (
              <Eye className="size-3.5" />
            ) : (
              <EyeOff className="size-3.5" />
            )}
            <Switch
              aria-label={enabled ? "Hide section" : "Show section"}
              checked={enabled}
              onCheckedChange={(checked) =>
                onChange({ ...section, enabled: checked })
              }
            />
          </label>
          <Button
            ref={renameButtonRef}
            size="icon-sm"
            variant="ghost"
            aria-label={renaming ? "Done renaming" : "Rename section"}
            // Prevent the button press from blurring the rename input first
            // (which would fire onBlur → renaming=false, then this toggle would
            // flip it back to true and trap the user in rename mode).
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => (renaming ? commitRename() : startRename())}
          >
            {renaming ? (
              <Check className="size-3.5" />
            ) : (
              <Pencil className="size-3.5" />
            )}
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Move ${sectionName} up`}
            disabled={!onMoveUp}
            onClick={onMoveUp}
          >
            <ArrowUp className="size-3.5" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Move ${sectionName} down`}
            disabled={!onMoveDown}
            onClick={onMoveDown}
          >
            <ArrowDown className="size-3.5" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Delete ${sectionName}`}
            className="text-muted-foreground hover:text-destructive"
            onClick={async () => {
              const ok = await confirm({
                title: `Delete ${sectionName}?`,
                // Saved versions keep it: the confirm says Version history
                // restores it.
                description:
                  "This deletes the section and everything in it. Version history keeps your saved versions, so you can restore it.",
                confirmLabel: "Delete section",
                destructive: true,
              });
              if (ok) onDelete();
            }}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="mt-3">
        {section.type === "entries" ? (
          <EntriesEditor
            entries={section.entries}
            onChange={(entries) => onChange({ ...section, entries })}
          />
        ) : (
          <BulletList
            value={section.bullets}
            onChange={(bullets) => onChange({ ...section, bullets })}
          />
        )}
      </div>
    </div>
  );
}

function EntriesEditor({
  entries,
  onChange,
}: {
  entries: ExtraSectionEntry[];
  onChange: (next: ExtraSectionEntry[]) => void;
}) {
  const { setEditingIndex, entryEditingProps, update } = useEntryEditing(
    entries,
    onChange,
    (e) => !e.heading,
  );

  return (
    <div className="flex flex-col gap-2">
      {entries.map((entry, i) => {
        const enabled = isEnabled(entry);
        return (
          <EditableCard
            key={i}
            name={entry.heading || "untitled item"}
            muted={!enabled}
            {...entryEditingProps(i)}
            extraActions={[
              createEnableAction(enabled, () => update(i, { enabled: !enabled })),
            ]}
            read={
              <div className="flex flex-col gap-2 pr-16">
                <div className="flex items-baseline justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-foreground text-sm font-semibold">
                      {entry.heading || (
                        <em className="opacity-60">Untitled item</em>
                      )}
                    </span>
                    <HiddenBadge enabled={enabled} />
                  </div>
                  <div className="text-muted-foreground text-xs whitespace-nowrap">
                    {entry.date || "—"}
                  </div>
                </div>
                {(entry.subheading || entry.location) && (
                  <div className="text-muted-foreground text-xs">
                    {[entry.subheading, entry.location]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
                {entry.link && (
                  <div className="text-muted-foreground truncate text-xs">
                    {entry.link}
                  </div>
                )}
                <BulletsRead bullets={entry.bullets} />
              </div>
            }
            edit={() => (
              <div className="grid gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Heading"
                    value={entry.heading}
                    onChange={(v) => update(i, { heading: v })}
                  />
                  <Field
                    label="Subheading"
                    optional
                    value={entry.subheading ?? ""}
                    onChange={(v) => update(i, { subheading: v })}
                  />
                  <Field
                    label="Location"
                    optional
                    value={entry.location ?? ""}
                    onChange={(v) => update(i, { location: v })}
                  />
                  <Field
                    label="Date"
                    optional
                    value={entry.date ?? ""}
                    onChange={(v) => update(i, { date: v })}
                  />
                  <Field
                    label="Link"
                    optional
                    value={entry.link ?? ""}
                    onChange={(v) => update(i, { link: v })}
                    hint="Starts with https://"
                  />
                </div>
                <BulletList
                  value={entry.bullets}
                  onChange={(bullets) => update(i, { bullets })}
                />
              </div>
            )}
          />
        );
      })}
      <AddEntryButton
        label="Add item"
        onClick={() => {
          onChange([...entries, emptyEntry()]);
          setEditingIndex(entries.length);
        }}
      />
    </div>
  );
}

function AddSectionDialog({
  open,
  onOpenChange,
  existingKeys,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingKeys: string[];
  onAdd: (section: ExtraSection) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<ExtraSectionType>("entries");

  const reset = () => {
    setName("");
    setType("entries");
  };

  const nameCollides = isCoreSectionTitle(name);

  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed || nameCollides) return;
    onAdd(newSection(trimmed, type, existingKeys));
    reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Add a section</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-1.5">
            {SECTION_PRESETS.map((preset) => (
              <Button
                key={preset.id}
                variant="outline"
                size="sm"
                onClick={() => {
                  setName(preset.title);
                  setType(preset.type);
                }}
              >
                {preset.label}
              </Button>
            ))}
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="new-section-name">Name</Label>
            <Input
              id="new-section-name"
              autoFocus
              aria-invalid={nameCollides}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
            />
            {nameCollides && (
              <span className="text-destructive text-xs">
                {TITLE_COLLISION_MESSAGE}
              </span>
            )}
          </div>

          <div className="grid gap-1.5">
            <Label>Layout</Label>
            <div className="flex gap-1.5">
              <TypeChoice
                active={type === "entries"}
                title={SECTION_TYPE_LABELS.entries}
                hint="Each with a title, details and bullets"
                onClick={() => setType("entries")}
              />
              <TypeChoice
                active={type === "bullets"}
                title={SECTION_TYPE_LABELS.bullets}
                hint="A simple list"
                onClick={() => setType("bullets")}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || nameCollides}>
            Add section
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TypeChoice({
  active,
  title,
  hint,
  onClick,
}: {
  active: boolean;
  title: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex flex-1 flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left transition-colors",
        active
          ? "border-primary bg-primary/5"
          : "border-input hover:border-border",
      )}
    >
      <span className="text-sm font-medium">{title}</span>
      <span className="text-muted-foreground text-xs">{hint}</span>
    </button>
  );
}
