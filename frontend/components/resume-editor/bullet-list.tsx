"use client";

import { useId, useRef } from "react";
import { ArrowDown, ArrowUp, ArrowUpToLine, Ellipsis, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  DragHandle,
  SortableItem,
  SortableList,
  rowSuccessor,
  useRowIds,
} from "@/components/ui/sortable-list";
import { Textarea } from "@/components/ui/textarea";
import { focusIfDropped } from "@/lib/focus";
import { move } from "@/lib/utils";

/**
 * An entry's bullets while it is being edited. Each row is a drag handle, its text and a ⋯ menu: drag
 * to reorder (pointer or keyboard), or Move to top / up / down and Delete from the menu. The menu is the
 * click-only path WCAG 2.5.7 asks for beside dragging; it replaced three stacked buttons per row that made
 * every row as tall as the stack.
 */
export function BulletList({
  label = "Bullets",
  itemLabel = "Bullet",
  value,
  onChange,
}: {
  /** The group's name ("Bullets"). */
  label?: string;
  /** One row's name ("Bullet"): "Bullet 2 of 5", never "Bullets 2 of 5". */
  itemLabel?: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const labelId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const addRef = useRef<HTMLButtonElement>(null);
  const { ids, moveId, removeId, addId } = useRowIds(value.length);
  const noun = itemLabel.toLowerCase();

  const moveRow = (from: number, to: number) => {
    if (to < 0 || to >= value.length || from === to) return;
    moveId(from, to);
    onChange(move(value, from, to));
  };

  const deleteRow = (index: number) => {
    // The row and its menu leave together: focus goes to the next bullet's text, else the previous
    // one's, else Add bullet. Read now, while the row is still in the document.
    const row = listRef.current?.querySelector(`[data-row-id="${ids[index]}"]`);
    const next = rowSuccessor(row, "textarea", () => addRef.current);
    removeId(index);
    onChange(value.filter((_, i) => i !== index));
    // After the menu has closed and tried its own return (to the ⋯ that is gone).
    requestAnimationFrame(() => focusIfDropped(next()));
  };

  return (
    <div className="space-y-2" role="group" aria-labelledby={labelId}>
      <span id={labelId} className="text-label-large">
        {label}
      </span>
      <div ref={listRef} className="space-y-2">
        <SortableList ids={ids} itemLabel={(i) => `${itemLabel} ${i + 1}`} onMove={moveRow}>
          {value.map((bullet, i) => (
            <SortableItem key={ids[i]} id={ids[i]} className="flex items-start gap-1">
              {(handle) => (
                <>
                  <DragHandle {...handle} label={`Drag ${noun} ${i + 1} to move it`} className="mt-1.5" />
                  <Textarea
                    rows={2}
                    // Position matters here: the handle and the menu beside each row are only
                    // meaningful if you can tell which bullet you are on.
                    aria-label={`${itemLabel} ${i + 1} of ${value.length}`}
                    value={bullet}
                    onChange={(e) =>
                      onChange(value.map((b, idx) => (idx === i ? e.target.value : b)))
                    }
                  />
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          className="text-muted-foreground mt-1"
                          // Names carry the position, like the textarea: "More actions" on every row
                          // tells a screen-reader user nothing about WHICH bullet it acts on.
                          aria-label={`More actions for ${noun} ${i + 1}`}
                        >
                          <Ellipsis />
                        </Button>
                      }
                    />
                    <DropdownMenuContent align="end" className="w-auto min-w-44">
                      <DropdownMenuItem disabled={i === 0} onClick={() => moveRow(i, 0)}>
                        <ArrowUpToLine /> Move to top
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={i === 0} onClick={() => moveRow(i, i - 1)}>
                        <ArrowUp /> Move up
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={i === value.length - 1}
                        onClick={() => moveRow(i, i + 1)}
                      >
                        <ArrowDown /> Move down
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" onClick={() => deleteRow(i)}>
                        <Trash2 /> Delete {noun}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </>
              )}
            </SortableItem>
          ))}
        </SortableList>
      </div>
      <Button
        ref={addRef}
        size="sm"
        variant="outline"
        onClick={() => {
          addId();
          onChange([...value, ""]);
        }}
      >
        Add {noun}
      </Button>
    </div>
  );
}
