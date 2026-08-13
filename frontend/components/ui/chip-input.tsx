"use client";

import { useRef, useState } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Chip/pill editor for a list of strings. Enter or comma commits the draft;
 * Backspace on an empty draft removes the last chip; paste splits on commas
 * and newlines; chips drag-reorder via native HTML5 DnD. Click a chip's
 * text to edit it in place: Enter or blur commits the trimmed value
 * verbatim (no comma-splitting) at the same index, Esc cancels, and an
 * empty commit deletes the chip.
 */
export function ChipListInput({
  id,
  value,
  onChange,
  placeholder = "Add…",
  className,
}: {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const dragFrom = useRef<number | null>(null);

  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  // Unmounting the edit <input> (Esc, or the slot disappearing) fires a
  // native blur synchronously, so commit/cancel must be idempotent.
  const editSession = useRef<{
    index: number | null;
    draft: string;
    original: string | null;
    done: boolean;
  }>({
    index: null,
    draft: "",
    original: null,
    done: true,
  });

  const commit = (raw: string) => {
    const items = raw
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (items.length) onChange([...value, ...items]);
  };

  const removeAt = (i: number) =>
    onChange(value.filter((_, idx) => idx !== i));

  const reorder = (from: number, to: number) => {
    if (from === to) return;
    const next = [...value];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  const startEdit = (i: number, text: string) => {
    editSession.current = { index: i, draft: text, original: text, done: false };
    setEditingIndex(i);
    setEditDraft(text);
  };

  const updateEditDraft = (text: string) => {
    editSession.current.draft = text;
    setEditDraft(text);
  };

  const commitEdit = () => {
    const session = editSession.current;
    if (session.done || session.index === null) return;
    session.done = true;
    setEditingIndex(null);
    // value can shrink out from under a mid-edit chip (e.g. a KB import
    // rewriting the list); the index is only trustworthy if that slot still
    // holds what editing started on.
    if (value[session.index] !== session.original) return;
    const text = session.draft.trim();
    const next = [...value];
    if (text) next[session.index] = text;
    else next.splice(session.index, 1);
    onChange(next);
  };

  const cancelEdit = () => {
    editSession.current.done = true;
    setEditingIndex(null);
  };

  return (
    <div
      className={cn(
        // min-w-0: a flex/grid item defaults to min-width:auto, so an editing
        // chip's definite width would push this container past its cell
        // instead of letting the chip's max-width cap it (SYSTEM.md §8).
        "border-input focus-within:ring-ring/50 flex min-h-9 min-w-0 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm focus-within:ring-2",
        className,
      )}
    >
      {value.map((item, i) => {
        const isEditing = i === editingIndex;
        return (
          <span
            key={`${item}-${i}`}
            draggable={!isEditing}
            onDragStart={() => (dragFrom.current = i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (dragFrom.current !== null) reorder(dragFrom.current, i);
              dragFrom.current = null;
            }}
            className="bg-muted text-foreground/90 inline-flex cursor-grab items-center gap-1 rounded-md px-2 py-0.5 active:cursor-grabbing"
            style={{ maxWidth: "100%" }}
          >
            {isEditing ? (
              <input
                ref={(el) => {
                  if (el && document.activeElement !== el) {
                    el.focus();
                    el.setSelectionRange(el.value.length, el.value.length);
                  }
                }}
                value={editDraft}
                onChange={(e) => updateEditDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    commitEdit();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    e.stopPropagation();
                    cancelEdit();
                  }
                }}
                onBlur={commitEdit}
                className="min-w-0 max-w-full bg-transparent outline-none"
                style={{ width: `${Math.max(editDraft.length + 1, 4)}ch` }}
                aria-label={`Edit ${item}`}
              />
            ) : (
              <>
                <button
                  type="button"
                  className="cursor-text"
                  aria-label={`Edit ${item}`}
                  onClick={() => startEdit(i, item)}
                >
                  {item}
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${item}`}
                  className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-sm after:absolute after:-inset-2 after:content-['']"
                  onClick={() => removeAt(i)}
                >
                  <X className="size-3" />
                </button>
              </>
            )}
          </span>
        );
      })}
      <input
        id={id}
        value={draft}
        placeholder={value.length === 0 ? placeholder : ""}
        className="placeholder:text-muted-foreground min-w-24 flex-1 bg-transparent outline-none"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit(draft);
            setDraft("");
          } else if (e.key === "Backspace" && draft === "" && value.length) {
            removeAt(value.length - 1);
          }
        }}
        onPaste={(e) => {
          const text = e.clipboardData.getData("text");
          if (/[,\n]/.test(text)) {
            e.preventDefault();
            commit(draft + text);
            setDraft("");
          }
        }}
        onBlur={() => {
          if (draft.trim()) {
            commit(draft);
            setDraft("");
          }
        }}
      />
    </div>
  );
}
