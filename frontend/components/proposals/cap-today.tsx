"use client";

import { RotateCw } from "lucide-react";

import { RetryChip } from "@/components/retry-chip";
import { useProposalFunnel } from "@/hooks/use-proposal-funnel";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";

/**
 * "Applications per day: 2 of 10 used in the last 24 hours" under the Agent inbox subtitle: the one number from the old
 * funnel strip that bears on triage, because each submit a connected agent
 * makes takes a slot. The whole funnel lives in Analytics › Overview (Agent
 * pipeline) on the same query.
 *
 * The window is the backend's rolling 24 hours (services/proposals.cap_status),
 * so the line says "the last 24 hours", never "today"; "Applications per day"
 * is the setting's name (Settings › Connected agents). While loading it shows nothing, which claims
 * nothing. A failed first load is its own state, a retry chip, never a silent
 * blank (docs/frontend-conventions.md, "A failed fetch is a THIRD state").
 * Analytics' Agent pipeline card shows the same line, so both say it one way.
 */
export function CapToday({ className }: { className?: string }) {
  const query = useProposalFunnel();
  if (isLoadFailure(query)) {
    return (
      <RetryChip
        className="text-muted-foreground mt-0.5 inline-flex items-center gap-1 text-xs underline-offset-4 hover:underline"
        title="Retry loading the daily submission cap"
        icon={<RotateCw className="size-3" aria-hidden="true" />}
        label="Couldn't load the daily cap. Retry"
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const cap = query.data?.cap;
  if (!cap) return null;
  return (
    <p className={cn("mt-0.5 text-xs tabular-nums", className)}>
      Applications per day: {cap.reserved_last_24h} of {cap.max_per_day} used in the last 24 hours
    </p>
  );
}
