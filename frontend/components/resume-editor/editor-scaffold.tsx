"use client";

import { Eye, EyeOff, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { move } from "@/lib/utils";

/** Determines if an entry is enabled (defaults to true if undefined). */
export function isEntryEnabled(entry: { enabled?: boolean }): boolean {
  return entry.enabled !== false;
}

/** Generates standard list reordering and deletion callbacks for EditableCard. */
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
