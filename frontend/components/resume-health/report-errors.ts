import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import {
  CONTENT_CHANGED_HINT,
  isContentChangedError,
} from "@/lib/health-report";

/** The standard content-changed toast, with a Check again action when available. */
export function toastContentChanged(onReanalyze?: () => void) {
  toast.error(CONTENT_CHANGED_HINT, {
    action: onReanalyze
      ? { label: "Check again", onClick: () => onReanalyze() }
      : undefined,
  });
}

/** Error handler for draft/apply calls: content-changed 409s get the standard
 * toast, anything else "Couldn't <what>." (a draft passes "write new wording"). */
export function toastRewriteError(
  err: unknown,
  onReanalyze?: () => void,
  what = "apply the change",
) {
  if (err instanceof ApiError && isContentChangedError(err)) {
    toastContentChanged(onReanalyze);
    return;
  }
  toast.error(couldnt(what, err));
}
