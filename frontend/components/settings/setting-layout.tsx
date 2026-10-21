"use client";

import type { MouseEventHandler, ReactNode } from "react";
import { Check, Trash2 } from "lucide-react";

import { IconButton } from "@/components/icon-button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * The one vertical rhythm of a settings or profile card (docs/frontend-conventions.md, "Settings
 * rhythm"): a card body is a `grid gap-6` stack of blocks; fields in a block sit `grid gap-4`, in
 * columns only by the card's own width (`@lg/setting`, `@2xl/setting`); a field is `grid gap-1.5`
 * with a default-size `Label`; a long form is divided by group headings `gap-8` apart, never by rules;
 * the last block is the actions row.
 */

/** Group headings: the career history read view's `title-small` style. Autofill's legends use it. */
export const GROUP_HEADING = "text-muted-foreground text-title-small";

/** The last row of a card body: Save and its siblings, right-aligned, secondary first. */
export const ACTION_ROW = "flex flex-wrap items-center justify-end gap-2";

/** A labelled switch, at least 44px tall. The label (which toggles it) fills the row, height, width
 *  and the gap before the switch, so a tap anywhere on the row toggles. It keeps its default size. */
export function SwitchRow({
  htmlFor,
  label,
  children,
}: {
  htmlFor: string;
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-11 items-center justify-between">
      <Label htmlFor={htmlFor} className="flex-1 self-stretch py-1.5 pr-4">
        {label}
      </Label>
      {children}
    </div>
  );
}

/**
 * A two- or three-way choice as one row of pills (docs/design-system/components/SegmentedToggle, the
 * `source-toggle.tsx` look): the picked one is `secondary-container` with a leading Check and
 * `aria-pressed`, since the tonal fill alone is too faint to say "on". Nothing is pressed while
 * `value` is unknown (the theme before hydration). Named by `labelledBy`, else `label`.
 */
export function SegmentedChoice<T extends string>({
  label,
  labelledBy,
  describedBy,
  value,
  options,
  onChange,
}: {
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  value: T | undefined;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={labelledBy ? undefined : label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      className="inline-flex h-8 items-center justify-self-start rounded-full border p-0.5"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-3 text-label-medium transition-colors duration-150",
            value === option.value
              ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {value === option.value && <Check className="size-3" aria-hidden="true" />}
          {option.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Remove one entry. Muted at rest and destructive only on hover or focus: a column of solid red icons
 * shouted "danger" at every row. Stays focusable while a removal runs (every Remove disables together).
 */
export function RemoveButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  onClick: MouseEventHandler<HTMLButtonElement>;
}) {
  return (
    <IconButton
      label={label}
      icon={<Trash2 />}
      focusableWhenDisabled
      disabled={disabled}
      className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:text-destructive data-disabled:pointer-events-none data-disabled:opacity-50 dark:hover:bg-destructive/20 shrink-0"
      onClick={onClick}
    />
  );
}
