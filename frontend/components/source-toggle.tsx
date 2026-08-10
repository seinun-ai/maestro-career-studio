"use client";

import { cn } from "@/lib/utils";

export const SOURCES = ["all", "user", "agent"] as const;
export type SourceFilter = (typeof SOURCES)[number];

/** Segmented All / You / Agent provenance filter — shared by Applications
 * tracker and Analytics Overview. */
export function SourceToggle({
  value,
  onChange,
  className,
}: {
  value: SourceFilter;
  onChange: (next: SourceFilter) => void;
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
          className={cn(
            "h-7 cursor-pointer rounded-full px-3 text-xs font-medium transition-colors duration-150",
            value === s
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {s === "all" ? "All" : s === "user" ? "You" : "Agent"}
        </button>
      ))}
    </div>
  );
}
