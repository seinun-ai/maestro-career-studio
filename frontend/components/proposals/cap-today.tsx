"use client";

import { RotateCw } from "lucide-react";

import { RetryChip } from "@/components/retry-chip";
import { useProposalFunnel } from "@/hooks/use-proposal-funnel";
import { isLoadFailure } from "@/lib/query-state";

/**
 * "Cap today 2/10" under the Agent inbox subtitle: the one number from the old
 * funnel strip that bears on triage, because each submit a connected agent
 * makes takes a slot. The whole funnel lives in Analytics › Overview (Agent
 * pipeline) on the same query.
 *
 * "Today" is the backend's rolling 24 hours (services/proposals.cap_status),
 * and the spoken text says so. While loading it shows nothing, which claims
 * nothing. A failed first load is its own state, a retry chip, never a silent
 * blank (docs/frontend-conventions.md, "A failed fetch is a THIRD state").
 */
export function CapToday() {
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
    <p className="mt-0.5 text-xs tabular-nums">
      <span aria-hidden="true">
        Cap today {cap.reserved_last_24h}/{cap.max_per_day}
      </span>
      <span className="sr-only">
        Daily submission cap: {cap.reserved_last_24h} of {cap.max_per_day} used in the last 24 hours
      </span>
    </p>
  );
}
