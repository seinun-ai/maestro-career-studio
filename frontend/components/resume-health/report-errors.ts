import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  CONTENT_CHANGED_HINT,
  isContentChangedError,
} from "@/lib/health-report";

/** The standard content-changed toast, with a Re-analyze action when available. */
export function toastContentChanged(onReanalyze?: () => void) {
  toast.error(CONTENT_CHANGED_HINT, {
    action: onReanalyze
      ? { label: "Re-analyze", onClick: () => onReanalyze() }
      : undefined,
  });
}

/** Error handler for draft/apply calls: content-changed 409s get the standard
 * toast, anything else a plain error toast. */
export function toastRewriteError(err: unknown, onReanalyze?: () => void) {
  if (err instanceof ApiError && isContentChangedError(err)) {
    toastContentChanged(onReanalyze);
    return;
  }
  toast.error(err instanceof Error ? err.message : String(err));
}
