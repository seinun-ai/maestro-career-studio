"use client";

import type { ReactNode, Ref } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Select mode's quiet switch, as in Photos: "Select" puts a checkbox on every row and the bar at the bottom,
 * "Done" takes them away. Shared by the Agent inbox and Jobs, so the two lists pick rows one way.
 */
export function SelectToggle({
  selecting,
  onClick,
  ref,
  className,
}: {
  selecting: boolean;
  onClick: () => void;
  ref?: Ref<HTMLButtonElement>;
  className?: string;
}) {
  return (
    <Button ref={ref} type="button" variant="ghost" size="sm" className={cn("shrink-0", className)} onClick={onClick}>
      {selecting ? "Done" : "Select"}
    </Button>
  );
}

/**
 * Select mode's bar, on screen until Done (Photos' model: pick rows, then act). The caller passes only the
 * actions every picked row allows, the ones each row's own controls offer; a pick no action fits says so in
 * `hint`. Its buttons stay focusable while they run, and the list hands focus on when an action or Done takes
 * the bar away. Shared by the Agent inbox and Jobs.
 */
export function SelectionBar({
  selectedCount,
  nothingFits,
  hint,
  pending,
  onDone,
  children,
}: {
  selectedCount: number;
  /** Rows are picked and no action fits all of them: `hint` says what to pick instead. */
  nothingFits: boolean;
  hint: string;
  /** An action runs: Done waits, focusable and dimmed. */
  pending?: boolean;
  onDone: () => void;
  children: ReactNode;
}) {
  return (
    // data-slot: globals.css keeps a focused row above this fixed bar.
    <div
      data-slot="bulk-bar"
      className="bg-background/95 supports-backdrop-filter:backdrop-blur-sm animate-in slide-in-from-bottom-2 fade-in-0 duration-(--duration-short4) ease-(--ease-emphasized-decelerate) fixed inset-x-0 bottom-0 z-40 border-t px-4 py-3"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-2">
        <span role="status" className="text-title-small tabular-nums">
          {selectedCount > 0 ? `${selectedCount} selected` : "Pick the jobs to act on"}
        </span>
        {children}
        {nothingFits ? <span className="text-muted-foreground text-body-small">{hint}</span> : null}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          // Beside the actions, not at the far end: toasts land in the bottom-right corner over it.
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={onDone}
          disabled={pending}
          focusableWhenDisabled
        >
          Done
        </Button>
      </div>
    </div>
  );
}
