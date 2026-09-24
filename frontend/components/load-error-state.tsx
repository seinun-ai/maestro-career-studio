"use client";

import { TriangleAlert } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useFocusHandoff } from "@/hooks/use-focus-return";
import { useLastSeen } from "@/hooks/use-last-seen";
import { cn } from "@/lib/utils";

/**
 * The one "this didn't load" state.
 *
 * The failure it exists for is silent: react-query leaves `data` undefined after
 * an error, so `if (isLoading || !data)` never lets go and a list built from
 * `data ?? []` renders its EMPTY state. The Applications tracker showed the
 * new-user onboarding card to anyone whose pipeline failed to fetch — the app
 * confidently reporting the opposite of the truth.
 *
 * Distinct from `EmptyState` on purpose, and the distinction is the whole point:
 * empty means "there is nothing here", this means "we could not find out". The
 * copy therefore never says what the data is, only that reading it failed, and
 * it always offers the retry — a failed fetch is usually transient, and without
 * a retry the only affordance is a full page reload.
 *
 * `title` defaults to the generic sentence; pass one when the surface can name
 * what it was reading ("Couldn't load your applications."). `detail` is
 * `loadErrorDetail(error, thing)` (lib/error-text.ts): only a failure to reach
 * the app says to check that it's running; a 404 names the deleted thing.
 *
 * Try again stays focusable while `retrying` disables it, as the studio Save
 * does: a disabled native <button> drops a keyboard user's focus to <body>.
 *
 * A retry keeps this block mounted (`isLoadFailure` in the caller: react-query
 * clears the error while a data-less refetch runs) and keeps the last detail
 * while that refetch is in flight. When recovery unmounts it, focus moves to
 * the nearest `tabIndex={-1}` ancestor, or the main area.
 */
export function LoadErrorState({
  title = "Something didn't load.",
  detail,
  onRetry,
  retrying = false,
  action,
  className,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
  retrying?: boolean;
  action?: ReactNode;
  className?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  // Recovery unmounts this block, focused Try again included. Focus moves to the nearest tabIndex={-1}
  // ancestor (a panel that opted in: the Formatting panel's body, the ATS score panel) or the main area.
  useFocusHandoff(rootRef);
  // A retry clears the query's error while it runs; keep the words until it answers.
  const shownDetail = useLastSeen(detail);
  return (
    <div
      ref={rootRef}
      role="alert"
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed py-16 text-center",
        className,
      )}
    >
      <TriangleAlert className="text-muted-foreground/50 size-8" />
      <div className="min-w-0 px-6">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {shownDetail ?? "Something went wrong. Try again."}
        </p>
      </div>
      {onRetry ? (
        <Button
          variant="outline"
          onClick={onRetry}
          disabled={retrying}
          focusableWhenDisabled
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
        >
          {retrying ? "Retrying…" : "Try again"}
        </Button>
      ) : null}
      {action}
    </div>
  );
}
