"use client";

import { useState, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface EditableCardAction {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}

export function EditableCard({
  read,
  edit,
  initialEditing = false,
  editing: editingProp,
  onEditingChange,
  onMoveUp,
  onMoveDown,
  onDelete,
  extraActions,
  className,
  muted = false,
}: {
  read: ReactNode;
  edit: (close: () => void) => ReactNode;
  initialEditing?: boolean;
  /** Controlled mode: pass `editing` + `onEditingChange` when edit-state must
   * survive list reorders (index-keyed lists cannot hold it internally). */
  editing?: boolean;
  onEditingChange?: (editing: boolean) => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDelete?: () => void;
  extraActions?: EditableCardAction[];
  className?: string;
  muted?: boolean;
}) {
  const [editingState, setEditingState] = useState(initialEditing);
  const editing = editingProp ?? editingState;
  const setEditing = (next: boolean) => {
    if (onEditingChange) onEditingChange(next);
    if (editingProp === undefined) setEditingState(next);
  };
  const hasMenu = Boolean(
    onMoveUp || onMoveDown || onDelete || extraActions?.length,
  );

  return (
    <div
      className={cn(
        "group/card border-border/0 hover:border-border/60 relative rounded-md border px-3 py-3 transition-colors",
        muted && "opacity-70",
        editing && "border-border bg-muted/20",
        className,
      )}
    >
      {!editing && (
        <div className="pointer-coarse:opacity-100 absolute top-2 right-2 flex items-center gap-0.5 opacity-0 transition-opacity group-hover/card:opacity-100 focus-within:opacity-100">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Edit"
            onClick={() => setEditing(true)}
          >
            <Pencil className="size-3.5" />
          </Button>
          {hasMenu && (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button size="icon-sm" variant="ghost" aria-label="More actions">
                    <MoreHorizontal className="size-3.5" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                {onMoveUp && (
                  <DropdownMenuItem onClick={onMoveUp}>
                    <ArrowUp className="size-3.5" /> Move up
                  </DropdownMenuItem>
                )}
                {onMoveDown && (
                  <DropdownMenuItem onClick={onMoveDown}>
                    <ArrowDown className="size-3.5" /> Move down
                  </DropdownMenuItem>
                )}
                {extraActions?.map((a) => (
                  <DropdownMenuItem
                    key={a.label}
                    disabled={a.disabled}
                    onClick={a.onClick}
                  >
                    {a.icon}
                    {a.label}
                  </DropdownMenuItem>
                ))}
                {onDelete && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={onDelete}
                    >
                      <Trash2 className="size-3.5" /> Delete
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      )}

      {editing ? (
        <div className="flex flex-col gap-3">
          {edit(() => setEditing(false))}
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setEditing(false)}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        read
      )}
    </div>
  );
}
