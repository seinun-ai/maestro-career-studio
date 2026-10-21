"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The Folded tier: a row that keeps advanced or rare things one click away.
 * The title on the left, a short summary of what is inside on the right (a count, a few words),
 * so the row says what it holds without opening. A closed panel is `hidden`: out of the tab
 * order and the accessibility tree. It keeps its own open state unless the caller passes `open`
 * and `onOpenChange` (a count elsewhere on the page that opens it, say). */
export function Fold({ title, summary, children, defaultOpen = false, open: openProp, onOpenChange, className }: {
  title: string;
  summary?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}) {
  const [openState, setOpenState] = useState(defaultOpen);
  const open = openProp ?? openState;
  const setOpen = (next: (open: boolean) => boolean) => {
    const value = next(open);
    if (openProp === undefined) setOpenState(value);
    onOpenChange?.(value);
  };
  const panelId = useId();
  return (
    <div data-slot="fold" className={cn("rounded-corner-md bg-card", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex h-13 w-full cursor-pointer items-center gap-3 rounded-corner-md px-5 text-left"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-[rotate] duration-(--duration-short3) ease-standard",
            open && "rotate-90",
          )}
        />
        <span className="min-w-0 flex-1 truncate text-title-small">{title}</span>
        {summary ? <span className="shrink-0 text-body-small text-muted-foreground tabular-nums">{summary}</span> : null}
      </button>
      <div id={panelId} hidden={!open} className="px-5 pb-5">
        {children}
      </div>
    </div>
  );
}
