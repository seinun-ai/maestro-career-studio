"use client";

import type { MouseEventHandler } from "react";
import { Trash2 } from "lucide-react";

import { IconButton } from "@/components/icon-button";

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
