import { Loader2 } from "lucide-react";

import type { SaveStatus } from "@/lib/studio";
import { cn } from "@/lib/utils";

/**
 * The studio's save-status line. `role="status"` makes it a polite live
 * region, so each change is announced once without stealing focus.
 *
 * It replaces the success toasts a Save used to fire (three per tailored
 * Save): a toast announces a moment and vanishes, while "is my work saved?"
 * is a question about NOW. Errors still toast, because they must interrupt.
 */
export function SaveStatusText({ status }: { status: SaveStatus }) {
  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap",
        status.tone === "dirty" && "text-amber-800 dark:text-amber-300",
      )}
    >
      {status.tone === "busy" ? (
        <Loader2 aria-hidden="true" className="size-3 animate-spin" />
      ) : (
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 rounded-full",
            status.tone === "dirty" ? "bg-amber-500" : "bg-emerald-500",
          )}
        />
      )}
      {status.label}
    </span>
  );
}
