"use client";

import { Braces, History as HistoryIcon, MoreHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * The ⋯ trigger plus the two overflow items BOTH studios carry — the raw-JSON
 * toggle and History. Task 6 required the two menus to mirror each other
 * byte-for-byte; a shared component is the structural form of that
 * requirement (see StudioToolbar's overflow rule for why these two live in
 * the menu at all). Studio-specific items render via `children`, after the
 * shared pair, or via `leading` above it — for an item that NAMES a current
 * value (the base studio's role) rather than performing a rare action.
 */
export function StudioOverflowMenu({
  rawMode,
  onToggleRaw,
  onHistory,
  triggerDisabled,
  leading,
  children,
}: {
  rawMode: boolean;
  onToggleRaw: () => void;
  onHistory: () => void;
  /** Base studio passes nothing; keep item-level gates on the items. */
  triggerDisabled?: boolean;
  /** Items rendered ABOVE the shared pair. */
  leading?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="More resume actions"
            disabled={triggerDisabled}
          >
            <MoreHorizontal />
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        {leading}
        {/* Rare, once-a-session — see StudioToolbar's overflow rule. */}
        <DropdownMenuItem onClick={onToggleRaw}>
          <Braces />
          {rawMode ? "Form view" : "Edit raw JSON"}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onHistory}>
          <HistoryIcon />
          History
        </DropdownMenuItem>
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
