"use client";

import type { MouseEventHandler, ReactNode } from "react";
import { Trash2 } from "lucide-react";

import { IconButton } from "@/components/icon-button";
import { Label } from "@/components/ui/label";

/**
 * The one vertical rhythm of a settings or profile card (docs/frontend-conventions.md, "Settings
 * rhythm"): a card body is a `grid gap-6` stack of blocks; fields in a block sit `grid gap-4`, in
 * columns only by the card's own width (`@lg/setting`, `@2xl/setting`); a field is `grid gap-1.5`
 * with a default-size `Label`; a long form is divided by group headings `gap-8` apart, never by rules;
 * the last block is the actions row.
 */

/** Group headings: the career history read view's uppercase tracked style. Autofill's legends use it. */
export const GROUP_HEADING =
  "text-muted-foreground text-xs font-semibold tracking-[0.12em] uppercase";

/** The last row of a card body: Save and its siblings, right-aligned, secondary first. */
export const ACTION_ROW = "flex flex-wrap items-center justify-end gap-2";

/** A labelled switch, at least 44px tall. The label (which toggles it) fills the row, height, width
 *  and the gap before the switch, so a tap anywhere on the row toggles. It keeps its default size;
 *  `leading-snug` only spaces its lines when it wraps at 375. */
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
      <Label htmlFor={htmlFor} className="flex-1 self-stretch py-1.5 pr-4 leading-snug">
        {label}
      </Label>
      {children}
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
