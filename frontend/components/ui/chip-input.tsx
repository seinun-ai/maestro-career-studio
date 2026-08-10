"use client";

import { useRef, useState } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Chip/pill editor for a list of strings. Enter or comma commits the draft;
 * Backspace on an empty draft removes the last chip; paste splits on commas
 * and newlines; chips drag-reorder via native HTML5 DnD.
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

  return (
    <div
      className={cn(
        "border-input focus-within:ring-ring/50 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm focus-within:ring-2",
        className,
      )}
    >
      {value.map((item, i) => (
        <span
          key={`${item}-${i}`}
          draggable
          onDragStart={() => (dragFrom.current = i)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (dragFrom.current !== null) reorder(dragFrom.current, i);
            dragFrom.current = null;
          }}
          className="bg-muted text-foreground/90 inline-flex cursor-grab items-center gap-1 rounded-md px-2 py-0.5 active:cursor-grabbing"
        >
          {item}
          <button
            type="button"
            aria-label={`Remove ${item}`}
            className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-sm after:absolute after:-inset-2 after:content-['']"
            onClick={() => removeAt(i)}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
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
