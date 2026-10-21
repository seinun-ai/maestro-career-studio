"use client";

import { Check } from "lucide-react";

import { PERIODS, type Period } from "@/lib/search-summary";
import { cn } from "@/lib/utils";

/** Analytics' period: 4 weeks, 12 weeks or All. The segmented look of the source toggle beside it (selected is
 * the tonal fill, a leading Check and `aria-pressed`). */
export function PeriodToggle({ value, onChange }: { value: Period; onChange: (next: Period) => void }) {
  return (
    <div className="inline-flex h-8 items-center rounded-full border p-0.5" role="group" aria-label="Period">
      {PERIODS.map((p) => (
        <button
          key={p.value}
          type="button"
          aria-pressed={value === p.value}
          onClick={() => onChange(p.value)}
          className={cn(
            "inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-3 text-label-medium transition-colors duration-150",
            value === p.value
              ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {value === p.value && <Check className="size-3" aria-hidden="true" />}
          {p.label}
        </button>
      ))}
    </div>
  );
}
