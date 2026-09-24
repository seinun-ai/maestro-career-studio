"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export const SOURCES = ["all", "user", "agent"] as const;
export type SourceFilter = (typeof SOURCES)[number];

/** Segmented provenance filter, shared by the Jobs page and Analytics Overview.
 * "Agents" are connected agents (MCP clients). The first segment's word is the
 * caller's: Jobs says "Tracked" (its default set leaves agent finds out) and
 * Analytics keeps "All" (every application). The values, and so `?source=`
 * deep links, are the same everywhere. */
export function SourceToggle({
  value,
  onChange,
  onPreview,
  allLabel = "All",
  label = "Filter by who found it",
  className,
}: {
  value: SourceFilter;
  onChange: (next: SourceFilter) => void;
  /** A segment is hovered or focused: its list may be about to show. */
  onPreview?: (next: SourceFilter) => void;
  /** The `all` segment's word. */
  allLabel?: string;
  /** The group's accessible name. */
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex h-8 items-center rounded-full border p-0.5",
        className,
      )}
      role="group"
      aria-label={label}
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
          {s === "all" ? allLabel : s === "user" ? "Yours" : "Agents"}
        </button>
      ))}
    </div>
  );
}
