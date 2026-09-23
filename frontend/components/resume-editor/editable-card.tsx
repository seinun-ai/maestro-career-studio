"use client";

import { useRef, useState, type ReactNode, type Ref } from "react";
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
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
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
  // Edit and Done each unmount themselves: opening focuses the editor's first
  // field, closing (Done, or the editor's own `close`) the pencil.
  const pencilRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLDivElement>(null);
  const focusNext = useFocusOnNextCommit();
  const setEditing = (next: boolean) => {
    if (onEditingChange) onEditingChange(next);
    if (editingProp === undefined) setEditingState(next);
    focusNext(next ? editRef : pencilRef);
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
            ref={pencilRef}
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
        <EditPane ref={editRef} edit={edit} onClose={() => setEditing(false)} />
      ) : (
        read
      )}
    </div>
  );
}

/**
 * The open editor and its Done. `onClose` returns focus to the pencil, so it
 * reaches `edit` as a prop: called straight from the card's render, a closure
 * over the focus refs fails the React Compiler lint.
 */
function EditPane({
  ref,
  edit,
  onClose,
}: {
  ref: Ref<HTMLDivElement>;
  edit: (close: () => void) => ReactNode;
  onClose: () => void;
}) {
  return (
    <div ref={ref} className="flex flex-col gap-3">
      {edit(onClose)}
      <div className="flex justify-end">
        <Button size="sm" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}
