"use client";

import { useRef, useState, type RefObject } from "react";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeOff,
  Ellipsis,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DragHandle,
  SortableItem,
  SortableList,
  rowSuccessor,
} from "@/components/ui/sortable-list";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { focusIfDropped } from "@/lib/focus";
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
import { cn, move } from "@/lib/utils";

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
  // Where focus goes when the last section is deleted.
  const addSectionRef = useRef<HTMLButtonElement>(null);

  const replaceAt = (i: number, next: ExtraSection) =>
    onChange(value.map((s, idx) => (idx === i ? next : s)));

  const existingKeys = value.map((s) => s.key);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground text-body-small">
        Dates here don&apos;t count as work history.
      </p>

      {value.length === 0 ? (
        <p className="text-muted-foreground rounded-corner-md border border-dashed px-3 py-6 text-center text-body-medium italic">
          No other sections yet.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {/* Keyed by `section.key`, which a rename never changes: a dragged or moved card keeps its
              own open editor. */}
          <SortableList
            ids={existingKeys}
            itemLabel={(i) => value[i]?.title.trim() || "Untitled section"}
            onMove={(from, to) => onChange(move(value, from, to))}
          >
            {value.map((section, i) => (
              <SectionCard
                key={section.key}
                section={section}
                onChange={(next) => replaceAt(i, next)}
                addSectionRef={addSectionRef}
                {...cardReorderProps(value, i, onChange)}
              />
            ))}
          </SortableList>
        </div>
      )}

      <Button
        ref={addSectionRef}
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

/**
 * One custom section. At rest it reads like the other tabs: its name, its layout, and its content as
 * the resume shows it (a Simple list's bullets as a list; an Items-with-dates section's items as their
 * own cards). Edit opens the section's name and, for a Simple list, its bullets; Hide, Move and Delete
 * sit in ⋯ as on every other card, and the grip drags it.
 */
function SectionCard({
  section,
  onChange,
  onMoveUp,
  onMoveDown,
  onDelete,
  addSectionRef,
}: {
  section: ExtraSection;
  onChange: (next: ExtraSection) => void;
  addSectionRef: RefObject<HTMLButtonElement | null>;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDelete: () => void;
}) {
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);
  const enabled = isEnabled(section);
  // Title captured when editing begins: Escape in the name field puts it back, and a name that
  // would collide with a core section header (which the schema also rejects) can't be kept.
  const originalTitleRef = useRef(section.title);
  const titleCollides = editing && isCoreSectionTitle(section.title);
  // Names the handle, Edit and ⋯, which repeat on every section card.
  const sectionName = section.title.trim() || "this section";
  // Edit unmounts itself while the section is open; Done hands focus back to it.
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();

  const startEditing = () => {
    originalTitleRef.current = section.title;
    setEditing(true);
  };
  const finishEditing = () => {
    // Never keep an empty title (schema contract); a colliding one can't reach here (Done waits).
    if (!section.title.trim()) onChange({ ...section, title: "Untitled section" });
    setEditing(false);
    focusNext(editButtonRef);
  };

  return (
    <SortableItem id={section.key}>
      {(handle) => (
        <div
          ref={cardRef}
          className={cn(
            "rounded-corner-md border p-3",
            !enabled && "opacity-70",
            editing && "bg-surface-container-low",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <DragHandle {...handle} label={`Drag ${sectionName} to move it`} />
              <span className="truncate text-title-small">
                {section.title || <em className="opacity-60">Untitled section</em>}
              </span>
              <Badge variant="secondary" className="shrink-0 text-body-small">
                {SECTION_TYPE_LABELS[section.type]}
              </Badge>
              <HiddenBadge enabled={enabled} />
            </div>

            {!editing && (
              <div className="flex shrink-0 items-center gap-0.5">
                <Button
                  ref={editButtonRef}
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Edit ${sectionName}`}
                  onClick={startEditing}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        ref={menuRef}
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`More actions for ${sectionName}`}
                      >
                        <Ellipsis className="size-3.5" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" className="w-auto min-w-44">
                    <DropdownMenuItem onClick={() => onChange({ ...section, enabled: !enabled })}>
                      {enabled ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                      {enabled ? "Hide from resume" : "Show on resume"}
                    </DropdownMenuItem>
                    <DropdownMenuItem disabled={!onMoveUp} onClick={onMoveUp}>
                      <ArrowUp className="size-3.5" /> Move up
                    </DropdownMenuItem>
                    <DropdownMenuItem disabled={!onMoveDown} onClick={onMoveDown}>
                      <ArrowDown className="size-3.5" /> Move down
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={async () => {
                        // The card goes with a confirmed delete: focus moves to the next section's
                        // first control, read now while this card is in the document.
                        const next = rowSuccessor(
                          cardRef.current?.closest("[data-row-id]"),
                          'button[aria-label^="Drag "]',
                          () => addSectionRef.current,
                        );
                        const ok = await confirm({
                          title: `Delete ${sectionName}?`,
                          // Saved versions keep it: the confirm says Version history
                          // restores it.
                          description:
                            "This deletes the section and everything in it. Version history keeps your saved versions, so you can restore it.",
                          confirmLabel: "Delete section",
                          destructive: true,
                          // The item is gone once the menu closes: Cancel returns to ⋯.
                          returnFocus: () => menuRef.current,
                        });
                        if (!ok) return;
                        onDelete();
                        requestAnimationFrame(() => focusIfDropped(next()));
                      }}
                    >
                      <Trash2 className="size-3.5" /> Delete section
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            )}
          </div>

          <div className="mt-3 flex flex-col gap-3">
            {editing && (
              <div className="grid gap-1.5">
                <Label htmlFor={`section-name-${section.key}`}>Section name</Label>
                <Input
                  id={`section-name-${section.key}`}
                  autoFocus
                  aria-invalid={titleCollides}
                  aria-describedby={titleCollides ? `section-name-${section.key}-error` : undefined}
                  value={section.title}
                  onChange={(e) => onChange({ ...section, title: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      // Puts the name back; the section stays open.
                      e.preventDefault();
                      onChange({ ...section, title: originalTitleRef.current });
                    } else if (e.key === "Enter") {
                      e.preventDefault();
                      if (!titleCollides) finishEditing();
                    }
                  }}
                  className="max-w-sm"
                />
                {titleCollides && (
                  <span id={`section-name-${section.key}-error`} className="text-destructive text-body-small">
                    {TITLE_COLLISION_MESSAGE}
                  </span>
                )}
              </div>
            )}

            {section.type === "entries" ? (
              <EntriesEditor
                entries={section.entries}
                onChange={(entries) => onChange({ ...section, entries })}
              />
            ) : editing ? (
              <BulletList
                value={section.bullets}
                onChange={(bullets) => onChange({ ...section, bullets })}
              />
            ) : (
              <BulletsRead bullets={section.bullets} />
            )}

            {editing && (
              <div className="flex justify-end">
                <Button
                  size="sm"
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  // Focusable while a colliding name holds it: a disabled button drops focus.
                  focusableWhenDisabled
                  disabled={titleCollides}
                  onClick={finishEditing}
                >
                  Done
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </SortableItem>
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
                    <span className="text-foreground text-title-small">
                      {entry.heading || (
                        <em className="opacity-60">Untitled item</em>
                      )}
                    </span>
                    <HiddenBadge enabled={enabled} />
                  </div>
                  <div className="text-muted-foreground text-body-small whitespace-nowrap">
                    {entry.date || "—"}
                  </div>
                </div>
                {(entry.subheading || entry.location) && (
                  <div className="text-muted-foreground text-body-small">
                    {[entry.subheading, entry.location]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
                {entry.link && (
                  <div className="text-muted-foreground truncate text-body-small">
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
              <span className="text-destructive text-body-small">
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
        "flex flex-1 flex-col items-start gap-0.5 rounded-corner-sm border px-3 py-2 text-left transition-colors",
        active
          ? "border-primary bg-primary/5"
          : "border-input hover:border-border",
      )}
    >
      <span className="text-title-small">{title}</span>
      <span className="text-muted-foreground text-body-small">{hint}</span>
    </button>
  );
}
