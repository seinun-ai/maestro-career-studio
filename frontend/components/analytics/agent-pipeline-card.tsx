"use client";

import { LoadErrorState } from "@/components/load-error-state";
import { CapToday } from "@/components/proposals/cap-today";
import { Fold } from "@/components/ui/fold";
import { useProposalFunnel } from "@/hooks/use-proposal-funnel";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import type { ProposalFunnel } from "@/lib/types";

const STAGES: Array<{
  key: keyof ProposalFunnel;
  label: string;
  optional?: boolean;
}> = [
  { key: "captured", label: "Found" },
  { key: "proposed", label: "Proposed" },
  { key: "accepted", label: "Queued", optional: true },
  { key: "approved", label: "Approved" },
  { key: "submitted", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
];

// The funnel counts where each job IS (current statuses), not how far it once got.
const WHERE = "Where your connected agents' jobs stand now.";

/** The agent-hunt funnel, folded on Analytics: where your connected agents' jobs stand now (current statuses, not
 * how far each once got). Nothing at all while nothing has been found, so someone without an agent sees no row; a
 * failed read still shows the row, with the failure inside. */
export function AgentPipelineFold() {
  const query = useProposalFunnel();
  const { data } = query;
  const failed = isLoadFailure(query);
  if (!failed && (data?.captured ?? 0) === 0) return null;

  const captured = data?.captured ?? 0;
  const stages = STAGES.filter((stage) => {
    if (!stage.optional) return true;
    return data != null && data[stage.key] != null;
  });

  return (
    <Fold title="Agent pipeline" summary={failed ? "Couldn't load" : `${captured} found`}>
      {failed ? (
        <LoadErrorState
          className="py-6"
          title="Couldn't load your agents' pipeline."
          detail={loadErrorDetail(query.error)}
          retrying={query.isFetching}
          onRetry={() => void query.refetch()}
        />
      ) : data ? (
        <div className="grid max-w-xl gap-3">
          <p className="text-muted-foreground text-body-small">{WHERE}</p>
          {stages.map((stage) => {
            const count = Number(data[stage.key] ?? 0);
            const widthPct =
              captured > 0 ? Math.min(100, Math.round((count / captured) * 100)) : 0;
            return (
              <div key={stage.key} className="grid gap-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-muted-foreground text-body-small">{stage.label}</span>
                  <span className="text-title-small tabular-nums">{count}</span>
                </div>
                <div className="bg-surface-container h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
          <CapToday className="text-muted-foreground mt-0" />
        </div>
      ) : null}
    </Fold>
  );
}
