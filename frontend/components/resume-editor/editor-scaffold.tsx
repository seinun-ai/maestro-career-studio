"use client";

import { useState } from "react";
import { Eye, EyeOff, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { move } from "@/lib/utils";

/** Determines if an entry is enabled (defaults to true if undefined). */
export function isEntryEnabled(entry: { enabled?: boolean }): boolean {
  return entry.enabled !== false;
}

/** Generates standard list reordering and deletion callbacks for EditableCard.
 *
 * Prefer `useEntryEditing` below: these callbacks reorder the DATA but say
 * nothing about which card is open, and an uncontrolled `EditableCard` in an
 * index-keyed list holds its open state against a POSITION. */
export function cardReorderProps<T>(
  value: T[],
  index: number,
  onChange: (next: T[]) => void,
) {
  return {
    onMoveUp: index > 0 ? () => onChange(move(value, index, index - 1)) : undefined,
    onMoveDown:
      index < value.length - 1
        ? () => onChange(move(value, index, index + 1))
        : undefined,
    onDelete: () => onChange(value.filter((_, idx) => idx !== index)),
  };
}

/** Reorder/delete callbacks that carry the OPEN CARD along with its entry.
 *
 * Entry lists render `value.map(...)` with `key={i}`, so React reconciles by
 * position. An `EditableCard` holding its own open/closed state therefore stays
 * with the SLOT: move the entry you are editing up one, and the card that ends
 * up open belongs to a different entry while yours silently collapses.
 *
 * The fix is to own the open index in the LIST and move it with the data —
 * which is only correct if every mutation that renumbers the list goes through
 * here. That is why this returns the reorder props rather than leaving callers
 * to combine `cardReorderProps` with their own index state: a caller that
 * forgets one of the two halves reintroduces the bug quietly.
 *
 * `isBlank` names what an unfilled entry looks like for this list — the first
 * one found opens on mount, which is how a just-added entry lands in edit mode.
 * The finding is shared here so a call site contributes only the predicate.
 */
export function useEntryEditing<T>(
  value: T[],
  onChange: (next: T[]) => void,
  isBlank: (entry: T) => boolean = () => false,
) {
  const [editingIndex, setEditingIndex] = useState<number | null>(() => {
    const blank = value.findIndex(isBlank);
    return blank === -1 ? null : blank;
  });

  const entryEditingProps = (index: number) => ({
    editing: editingIndex === index,
    onEditingChange: (next: boolean) => setEditingIndex(next ? index : null),
    onMoveUp:
      index > 0
        ? () => {
            onChange(move(value, index, index - 1));
            setEditingIndex((cur) =>
              cur === index ? index - 1 : cur === index - 1 ? index : cur,
            );
          }
        : undefined,
    onMoveDown:
      index < value.length - 1
        ? () => {
            onChange(move(value, index, index + 1));
            setEditingIndex((cur) =>
              cur === index ? index + 1 : cur === index + 1 ? index : cur,
            );
          }
        : undefined,
    onDelete: () => {
      onChange(value.filter((_, idx) => idx !== index));
      setEditingIndex((cur) =>
        cur === null || cur === index ? null : cur > index ? cur - 1 : cur,
      );
    },
  });

  /** Patch one entry in place. Lives here because every list wrote the same
   * three lines against the same `value`/`onChange` pair. */
  const update = (index: number, patch: Partial<T>) =>
    onChange(value.map((e, idx) => (idx === index ? { ...e, ...patch } : e)));

  return { editingIndex, setEditingIndex, entryEditingProps, update };
}

/** Renders standard active and archived count badge text. */
export function ActiveArchivedCount({
  items,
}: {
  items: Array<{ enabled?: boolean }>;
}) {
  const activeCount = items.filter(isEntryEnabled).length;
  const archivedCount = items.length - activeCount;

  return (
    <span className="text-muted-foreground">
      {activeCount} active
      {archivedCount > 0 ? ` · ${archivedCount} archived` : ""}
    </span>
  );
}

/** Creates standard enable/disable toggle action object for EditableCard extraActions. */
export function createEnableAction(enabled: boolean, onToggle: () => void) {
  return {
    label: enabled ? "Disable" : "Enable",
    icon: enabled ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />,
    onClick: onToggle,
  };
}

/** Renders standard ghost button for adding an entry to a section. */
export function AddEntryButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-muted-foreground hover:text-foreground mt-2 self-start"
      onClick={onClick}
    >
      <Plus className="size-3.5" /> {label}
    </Button>
  );
}
