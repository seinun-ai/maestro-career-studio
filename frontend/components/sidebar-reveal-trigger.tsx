"use client";

import { useEffect, useRef } from "react";

import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { useModKey } from "@/hooks/use-mod-key";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

/**
 * True when the app sidebar is off-screen (off-canvas on desktop, sheet
 * closed on mobile) — i.e. exactly when the floating reveal trigger below is
 * showing and top-left content needs clearance.
 */
export function useSidebarHidden(): boolean {
  const { open, isMobile, openMobile } = useSidebar();
  return isMobile ? !openMobile : !open;
}

/**
 * Shown in the main area when the sidebar is hidden. Convention (and the
 * owner's call, 2026-08-02): the reveal control lives TOP-LEFT, fixed to the
 * viewport — the same corner the in-sidebar trigger occupied, so it never
 * moves spatially. Room is made by SidebarGutter on the shell below, not by
 * each page — and never by moving the trigger.
 */
export function SidebarRevealTrigger() {
  const hidden = useSidebarHidden();
  const { isMobile } = useSidebar();
  const mod = useModKey();
  const ref = useRef<HTMLButtonElement>(null);
  const was = useRef(hidden);
  useEffect(() => {
    if (was.current === hidden) return; // transitions only: never on page load
    was.current = hidden;
    if (isMobile) return; // the Sheet owns its own focus
    const active = document.activeElement;
    const orphaned = !active || active === document.body;
    if (hidden) {
      // The in-sidebar control that had focus just went inert.
      if (orphaned || active?.closest('[data-slot="sidebar-container"]')) ref.current?.focus();
    } else if (orphaned) {
      // The pill that had focus just unmounted.
      document
        .querySelector<HTMLElement>('[data-slot="sidebar-container"] [data-sidebar="trigger"]')
        ?.focus();
    }
  }, [hidden, isMobile]);
  if (!hidden) return null;

  return (
    <div className="pointer-events-none fixed top-3 left-3 z-50">
      <SidebarTrigger
        ref={ref}
        className="pointer-events-auto rounded-md border bg-background/90 shadow-sm backdrop-blur"
        // Only on screen while the sidebar is hidden, so a press always shows it.
        title={`Show sidebar (${shortcutLabel(mod, "B")})`}
        aria-keyshortcuts="Meta+B Control+B"
      />
    </div>
  );
}

/**
 * Reserves a full-height gutter down the left edge of the main area while the
 * reveal trigger is showing.
 *
 * This replaces the per-page inline spacer that used to sit inside each header
 * row. That spacer only indented the ONE row it was dropped into, so a page's
 * title shifted right while everything below it stayed flush against the edge —
 * visibly ragged, and every page had to remember to opt in. A gutter on the
 * shared shell keeps the whole left edge consistent and cannot be forgotten.
 */
export function SidebarGutter({ children }: { children: React.ReactNode }) {
  const hidden = useSidebarHidden();
  return (
    <div
      // Skip-link target. It lives here rather than on a page's <main> because
      // this wrapper is the one element every route shares — a per-page id
      // would have to be remembered 20+ times, exactly the failure mode that
      // retired the per-page clearance spacer. tabIndex=-1 so the browser
      // actually moves focus here, not just the scroll position.
      id="main-content"
      tabIndex={-1}
      className={cn(
        "flex min-w-0 flex-1 flex-col transition-[padding] duration-200 outline-none",
        // Trigger is 28px (size-7) at left-3, so 3.5rem leaves 16px clearance.
        hidden && "pl-14",
      )}
    >
      {children}
    </div>
  );
}
