"use client";

import { ChartCard } from "@/components/charts/chart-kit";
import { CapToday } from "@/components/proposals/cap-today";
import { useProposalFunnel } from "@/hooks/use-proposal-funnel";
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

/** Horizontal agent-hunt funnel for Analytics Overview. Returns null when
 * nothing has been captured — no card noise for non-hunt users. */
export function AgentPipelineCard() {
  const { data, isLoading, error } = useProposalFunnel();

  if (!isLoading && !error && (data?.captured ?? 0) === 0) return null;

  const captured = data?.captured ?? 0;
  const stages = STAGES.filter((stage) => {
    if (!stage.optional) return true;
    return data != null && data[stage.key] != null;
  });

  return (
    <ChartCard
      title="Agent pipeline"
      // Counts of where each job is now (the funnel reads current statuses), not how far it once got.
      description="Where your connected agents' jobs stand now."
      isLoading={isLoading}
      error={error as Error | null}
    >
      {!data ? null : (
        <div className="grid gap-3">
          {stages.map((stage) => {
            const count = Number(data[stage.key] ?? 0);
            const widthPct =
              captured > 0 ? Math.min(100, Math.round((count / captured) * 100)) : 0;
            return (
              <div key={stage.key} className="grid gap-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-muted-foreground text-xs">{stage.label}</span>
                  <span className="text-sm font-medium tabular-nums">{count}</span>
                </div>
                <div className="bg-muted/50 h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-primary/10 h-full rounded-full"
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
          <CapToday className="text-muted-foreground mt-0" />
        </div>
      )}
    </ChartCard>
  );
}
