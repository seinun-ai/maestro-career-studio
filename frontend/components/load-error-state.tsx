"use client";

import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
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
 * what it was reading ("Couldn't load your applications."). `detail` carries the
 * server's own message where there is one worth showing.
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
  return (
    <div
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
          {detail ?? "The request failed. It may just be the backend restarting."}
        </p>
      </div>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Try again"}
        </Button>
      ) : null}
      {action}
    </div>
  );
}
