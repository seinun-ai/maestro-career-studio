"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type FilterChipOption<T extends string> = {
  value: T;
  label: string;
  /** Shown after the label. A string for a count that is not known yet ("…"). */
  count: number | string;
};

/**
 * Filter chips: one field narrowed by a few values, every choice and its count
 * on view (docs/design-system/components/FilterChips). Several can be on at
 * once; none on means no filter, so there is no "All" chip. A field with more
 * values than fit on one line stays a Select.
 *
 * Each chip is a toggle button (`aria-pressed`), like the segmented toggle,
 * and the tonal fill alone is too faint to say "on", so an on chip also
 * carries a leading Check. The group is named by `label`, and a chip's own name
 * says its count in one phrase (a count beside the label can drop out of it).
 */
export function FilterChips<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  /** The group's accessible name: what the chips filter. */
  label: string;
  options: readonly FilterChipOption<T>[];
  /** The values that are on. Empty means the field is not filtering. */
  value: ReadonlySet<T>;
  onChange: (next: Set<T>) => void;
  className?: string;
}) {
  const toggle = (v: T) => {
    const next = new Set(value);
    if (!next.delete(v)) next.add(v);
    onChange(next);
  };
  return (
    <div
      role="group"
      aria-label={label}
      className={cn("flex flex-wrap items-center gap-2", className)}
    >
      {options.map((o) => {
        const on = value.has(o.value);
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            aria-label={`${o.label} ${o.count}`}
            onClick={() => toggle(o.value)}
            className={cn(
              "inline-flex h-7 cursor-pointer items-center gap-1 rounded-full border px-3 text-label-medium whitespace-nowrap transition-colors duration-(--duration-short3) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              on
                ? "border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
                : "border-border text-muted-foreground hover:bg-surface-container",
            )}
          >
            {on && <Check className="size-3" aria-hidden="true" />}
            {o.label}
            <span className="tabular-nums">{o.count}</span>
          </button>
        );
      })}
    </div>
  );
}
