"use client";

import type { RefObject } from "react";
import { Braces, History as HistoryIcon, MoreHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { focusIfDropped } from "@/hooks/use-focus-return";

/**
 * The ⋯ trigger plus the two overflow items BOTH studios carry — the raw-JSON
 * toggle and History. Task 6 required the two menus to mirror each other
 * byte-for-byte; a shared component is the structural form of that
 * requirement (see StudioToolbar's overflow rule for why these two live in
 * the menu at all). Studio-specific items render via `children`, after the
 * shared pair, or via `leading` above it — for an item that NAMES a current
 * value (the base studio's role) rather than performing a rare action.
 *
 * `triggerRef` is the ⋯ button. Focus returns to it when the menu closes and
 * when any overlay an item opened closes (APG menu button): the item is gone
 * by then, and Base UI's default return target for a trigger-less overlay is
 * the last element it saw focused, which can be inside the closing overlay.
 * The overlays take it as `finalFocus`. The menu itself does not: an explicit
 * `finalFocus` also overrides an overlay's initial focus (History opened from
 * the keyboard landed back on ⋯), and its default already returns there after
 * a key press. After a click it returns nowhere, so once the popup is gone a
 * focus that fell to <body> moves to ⋯ (and only then: an overlay that took
 * focus keeps it).
 */
export function StudioOverflowMenu({
  triggerRef,
  rawMode,
  onToggleRaw,
  onHistory,
  triggerDisabled,
  leading,
  children,
}: {
  /** Focus returns here from the menu and from every overlay an item opens. */
  triggerRef: RefObject<HTMLButtonElement | null>;
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
    <DropdownMenu
      onOpenChangeComplete={(open) => {
        // Called just BEFORE the popup unmounts (focus is still on the item).
        if (!open) setTimeout(() => focusIfDropped(triggerRef.current), 0);
      }}
    >
      <DropdownMenuTrigger
        render={
          <Button
            ref={triggerRef}
            variant="ghost"
            size="icon-sm"
            aria-label="More resume actions"
            disabled={triggerDisabled}
          >
            <MoreHorizontal />
          </Button>
        }
      />
      {/* Sized to its labels. The primitive anchors a menu to its trigger's
          width, and this trigger is a 28px icon, so every item wrapped at the
          128px floor. Capped at the room Base UI measures beside the trigger,
          so a long "Copy slug: …" stays on screen; a slug's underscores are no
          break opportunity, so it wraps anywhere rather than clipping. */}
      <DropdownMenuContent
        align="end"
        className="w-auto min-w-56 max-w-(--available-width) wrap-anywhere"
      >
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
