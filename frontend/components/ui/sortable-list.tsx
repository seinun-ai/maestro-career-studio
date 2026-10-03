"use client";

import { useId, useState, type ComponentProps, type ReactNode } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type Modifier,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * A vertical list the user reorders by dragging a row's handle: with a pointer (mouse, pen, touch) or
 * the keyboard (focus the handle, Space to pick up, arrows to move, Space to drop, Escape to cancel),
 * each step announced to screen readers. Dragging is never the only way: every caller also offers a
 * click-only move (a menu's Move up/down, or up/down buttons), as WCAG 2.5.7 asks.
 *
 * `ids` are the rows' stable identities in their current order; `onMove(from, to)` reports a drop.
 * `itemLabel(index)` names a row in the announcements ("Bullet 2").
 */
export function SortableList({
  ids,
  itemLabel,
  onMove,
  disabled = false,
  children,
}: {
  ids: readonly string[];
  itemLabel: (index: number) => string;
  onMove: (from: number, to: number) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  // A stable id for the context: dnd-kit's own counter differs between the server render and the
  // client's, and the handles' aria-describedby then fails hydration.
  const contextId = useId();
  const sensors = useSensors(
    // A few pixels before a press becomes a drag, so clicking or focusing the handle stays a click.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const at = (id: UniqueIdentifier) => ids.indexOf(String(id));
  const place = (index: number) => `position ${index + 1} of ${ids.length}`;
  const announcements: Announcements = {
    onDragStart: ({ active }) => `Picked up ${itemLabel(at(active.id))}.`,
    onDragOver: ({ active, over }) =>
      over ? `${itemLabel(at(active.id))} is at ${place(at(over.id))}.` : undefined,
    onDragEnd: ({ active, over }) =>
      over
        ? `${itemLabel(at(active.id))} dropped at ${place(at(over.id))}.`
        : `${itemLabel(at(active.id))} dropped where it was.`,
    onDragCancel: ({ active }) =>
      `Moving cancelled. ${itemLabel(at(active.id))} stays at ${place(at(active.id))}.`,
  };
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = at(active.id);
    const to = at(over.id);
    if (from >= 0 && to >= 0) onMove(from, to);
  };
  return (
    <DndContext
      id={contextId}
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[verticalOnly]}
      onDragEnd={onDragEnd}
      accessibility={{
        announcements,
        screenReaderInstructions: {
          draggable:
            "To move this, press Space to pick it up, the up and down arrows to move it, and Space to drop it. Escape cancels.",
        },
      }}
    >
      <SortableContext items={[...ids]} strategy={verticalListSortingStrategy} disabled={disabled}>
        {children}
      </SortableContext>
    </DndContext>
  );
}

/** Rows move up and down only: a sideways drift while dragging read as the row coming loose. */
const verticalOnly: Modifier = ({ transform }) => ({ ...transform, x: 0 });

/** What a row hands its drag handle: spread it onto `DragHandle`. */
export type DragHandleProps = Pick<
  ReturnType<typeof useSortable>,
  "attributes" | "listeners" | "setActivatorNodeRef"
>;

/**
 * One row of a `SortableList`. It moves while dragged; `children` receives the handle's props, so the
 * handle can sit anywhere in the row. Extra props (a `data-*` marker, a className) land on the row.
 */
export function SortableItem({
  id,
  className,
  children,
  ...rest
}: {
  id: string;
  className?: string;
  children: (handle: DragHandleProps) => ReactNode;
} & Omit<ComponentProps<"div">, "children" | "id">) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  return (
    <div
      ref={setNodeRef}
      data-row-id={id}
      data-dragging={isDragging || undefined}
      // Translate only: a scale would stretch a row dragged over a taller one.
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(
        "relative rounded-corner-md data-dragging:z-10 data-dragging:bg-background data-dragging:shadow-md",
        className,
      )}
      {...rest}
    >
      {children({ attributes, listeners, setActivatorNodeRef })}
    </div>
  );
}

/** The grip a row is dragged by. `label` names the row: "Drag bullet 2 to move it". */
export function DragHandle({
  attributes,
  listeners,
  setActivatorNodeRef,
  label,
  className,
}: DragHandleProps & { label: string; className?: string }) {
  return (
    <button
      type="button"
      ref={setActivatorNodeRef}
      {...attributes}
      {...listeners}
      aria-label={label}
      className={cn(
        // touch-none: the browser would take a touch drag on the handle as a page scroll.
        "text-muted-foreground hover:text-foreground focus-visible:ring-ring flex size-7 shrink-0 cursor-grab touch-none items-center justify-center rounded-corner-sm outline-none focus-visible:ring-2 active:cursor-grabbing aria-disabled:cursor-default aria-disabled:opacity-40",
        className,
      )}
    >
      <GripVertical className="size-4" aria-hidden="true" />
    </button>
  );
}

/**
 * Where focus goes when `row` (a `SortableItem`) is removed: the next row's `control`, else the previous
 * row's, else `fallback`. Rows only: dnd-kit renders its hidden instructions and live region as the
 * list's last children, and a plain next-sibling walk (`focusSuccessor`) landed on those. Read NOW,
 * while the row is still in the document.
 */
export function rowSuccessor(
  row: Element | null | undefined,
  control: string,
  fallback: () => HTMLElement | null = () => null,
): () => HTMLElement | null {
  const siblings = row?.parentElement
    ? [...row.parentElement.children].filter((el) => el.hasAttribute("data-row-id"))
    : [];
  const at = row ? siblings.indexOf(row) : -1;
  const order = at < 0 ? [] : [siblings[at + 1], siblings[at - 1]];
  return () => {
    for (const neighbour of order) {
      if (!neighbour?.isConnected) continue;
      const target = neighbour.querySelector<HTMLElement>(control);
      if (target) return target;
    }
    return fallback();
  };
}

let rowSeq = 0;
const newRowId = () => `row-${(rowSeq += 1)}`;

/**
 * Stable ids for a list of plain values (bullets are bare strings, so their index is all they have).
 * A drag needs an id that travels with its row; keyed by index, a moved row would hand its textarea,
 * and the focus in it, to whatever landed in its place. Returns the ids and the list operations that
 * keep ids and values in step. A length change from outside (Raw JSON, a restore) pads or trims.
 */
export function useRowIds(count: number) {
  const [ids, setIds] = useState<string[]>(() => Array.from({ length: count }, newRowId));
  let current = ids;
  if (ids.length !== count) {
    current =
      ids.length > count
        ? ids.slice(0, count)
        : [...ids, ...Array.from({ length: count - ids.length }, newRowId)];
    setIds(current);
  }
  return {
    ids: current,
    moveId: (from: number, to: number) =>
      setIds((prev) => {
        const next = [...prev];
        const [id] = next.splice(from, 1);
        next.splice(to, 0, id);
        return next;
      }),
    removeId: (index: number) => setIds((prev) => prev.filter((_, i) => i !== index)),
    addId: () => setIds((prev) => [...prev, newRowId()]),
  };
}
