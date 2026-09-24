"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export const SOURCES = ["all", "user", "agent"] as const;
export type SourceFilter = (typeof SOURCES)[number];

/** Segmented All / You / Agents provenance filter — shared by Applications
 * tracker and Analytics Overview. "Agents" are connected agents (MCP clients). */
export function SourceToggle({
  value,
  onChange,
  onPreview,
  className,
}: {
  value: SourceFilter;
  onChange: (next: SourceFilter) => void;
  /** A segment is hovered or focused: its list may be about to show. */
  onPreview?: (next: SourceFilter) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex h-8 items-center rounded-full border p-0.5",
        className,
      )}
      role="group"
      aria-label="Filter by who found it"
    >
      {SOURCES.map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={value === s}
          onClick={() => onChange(s)}
          onPointerEnter={() => onPreview?.(s)}
          onFocus={() => onPreview?.(s)}
          className={cn(
            "inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-3 text-xs font-medium transition-colors duration-150",
            value === s
              ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {value === s && <Check className="size-3" aria-hidden="true" />}
          {s === "all" ? "All" : s === "user" ? "You" : "Agents"}
        </button>
      ))}
    </div>
  );
}
