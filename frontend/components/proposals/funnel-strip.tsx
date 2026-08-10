"use client";

import { useQuery } from "@tanstack/react-query";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { ProposalFunnel } from "@/lib/types";

const STAGES: Array<{ key: keyof ProposalFunnel; label: string }> = [
  { key: "captured", label: "Captured" },
  { key: "proposed", label: "Proposed" },
  { key: "accepted", label: "Accepted" },
  { key: "approved", label: "Approved" },
  { key: "submitted", label: "Submitted" },
  { key: "interviewing", label: "Interviewing" },
];

/** Top-of-inbox funnel: Captured → … → Interviewing + daily cap readout. */
export function FunnelStrip() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["proposals", "funnel"],
    queryFn: () => apiFetch<ProposalFunnel>("/api/proposals/funnel"),
  });

  // Card + CardContent, matching every other section block in the app. This
  // used to render as bare text floating between the page header and the
  // filters, which read as an unfinished fragment rather than a section.
  if (isLoading) {
    return <Skeleton className="h-[86px] w-full rounded-xl" />;
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-4">
          <p role="alert" className="text-destructive text-sm">
            {(error as Error).message}
          </p>
        </CardContent>
      </Card>
    );
  }
  if (!data) return null;

  return (
    <Card>
      <CardContent className="flex flex-wrap items-start gap-x-8 gap-y-4 py-4">
        {STAGES.map((stage) => (
          <div key={stage.key} className="flex flex-col gap-1">
            <span className="text-muted-foreground text-xs">{stage.label}</span>
            <span className="text-xl leading-none font-medium tabular-nums">
              {Number(data[stage.key] ?? 0)}
            </span>
          </div>
        ))}
        {data.cap ? (
          <div className="ml-auto flex flex-col gap-1 text-right">
            <span className="text-muted-foreground text-xs">Cap today</span>
            <span className="text-xl leading-none font-medium tabular-nums">
              {data.cap.reserved_last_24h}
              <span className="text-muted-foreground text-base font-normal">
                /{data.cap.max_per_day}
              </span>
            </span>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
