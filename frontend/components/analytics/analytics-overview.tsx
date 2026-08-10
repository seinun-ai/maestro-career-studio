"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { StatTile } from "@/components/analytics/stat-tile";

import { ActivityChart } from "@/components/analytics/activity-chart";
import { AgentPipelineCard } from "@/components/analytics/agent-pipeline-card";
import { AutofillCoverageCard } from "@/components/analytics/autofill-coverage-card";
import {
  SourceToggle,
  type SourceFilter,
} from "@/components/source-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { statusLabel } from "@/components/status-chip";
import { apiFetch } from "@/lib/api";
import type {
  ActivityResponse,
  BuildAreaRow,
  GapFrequencyRow,
  TailoringLiftRow,
} from "@/lib/types";
import { APPLICATION_STATUSES } from "@/lib/types";

export function AnalyticsOverview({
  onOpenTab,
}: {
  onOpenTab: (tab: string) => void;
}) {
  const [source, setSource] = useState<SourceFilter>("all");

  const activity = useQuery({
    queryKey: ["explore", "activity", "day", 4, source],
    queryFn: () => {
      const params = new URLSearchParams({ granularity: "day", weeks: "4" });
      if (source === "user" || source === "agent") params.set("source", source);
      return apiFetch<ActivityResponse>(`/api/explore/activity?${params}`);
    },
  });
  const lift = useQuery({
    queryKey: ["explore", "tailoring-lift", { role_category: null, level: null, employment_type: null }],
    queryFn: () => apiFetch<TailoringLiftRow[]>("/api/explore/tailoring-lift"),
  });
  const gaps = useQuery({
    queryKey: ["explore", "gap-frequency", "teaser"],
    queryFn: () =>
      apiFetch<GapFrequencyRow[]>("/api/explore/gap-frequency?limit=3"),
  });
  const buildAreas = useQuery({
    queryKey: ["explore", "build-areas", "teaser"],
    queryFn: () => apiFetch<BuildAreaRow[]>("/api/explore/build-areas?limit=20"),
  });

  const totals = activity.data?.totals;
  const allLift = (lift.data ?? []).find((row) => row.role_category === "all");
  // Excluding the wording tier is the point: those rows can be status "in_kb"
  // with n_jobs 0, so a zero-demand skill with no score to gain was surfacing as
  // a recommended quick win. Written as "not wording" rather than "is surface"
  // so a backend that predates the tier field degrades to the old behaviour
  // instead of emptying the card; for a current backend the two are equivalent,
  // since a build row is always status "missing".
  const quickWins = (buildAreas.data ?? [])
    .filter((row) => row.tier !== "wording" && row.status === "in_kb")
    .slice(0, 3);
  const statusCounts = activity.data?.status_counts ?? {};

  return (
    <div className="grid gap-4">
      <div className="flex justify-end">
        <SourceToggle value={source} onChange={setSource} />
      </div>

      {activity.isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : activity.error ? (
        <p role="alert" className="text-destructive text-sm">
          {(activity.error as Error).message}
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile
            label="Submitted · last 7 days"
            value={String(totals?.submitted_last7 ?? 0)}
            sub={`${totals?.submitted ?? 0} all time`}
          />
          <StatTile
            label="In flight"
            value={String(totals?.in_flight ?? 0)}
            sub="applied · interviewing · offered"
          />
          <StatTile
            label="At interview stage+"
            value={
              totals?.interview_rate != null
                ? `${Math.round(totals.interview_rate * 100)}%`
                : "—"
            }
            sub={
              totals?.submitted
                ? `currently, of ${totals.submitted} submitted`
                : "no submissions yet"
            }
          />
          <StatTile
            label="Avg tailoring lift"
            value={allLift ? `${allLift.avg_lift > 0 ? "+" : ""}${allLift.avg_lift}` : "—"}
            sub={allLift ? `ATS points over ${allLift.n} tailored` : "nothing tailored yet"}
          />
        </div>
      )}

      <ActivityChart source={source} />

      <div className="flex flex-wrap items-center gap-1.5">
        {APPLICATION_STATUSES.filter((status) => statusCounts[status]).map(
          (status) => (
            <span
              key={status}
              className="text-muted-foreground inline-flex h-7 items-center gap-1.5 rounded-full bg-muted/70 px-3 text-xs"
            >
              {statusLabel(status)}
              <span className="text-foreground font-medium">
                {statusCounts[status]}
              </span>
            </span>
          ),
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Most common gaps</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {gaps.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : gaps.error ? (
              <p role="alert" className="text-destructive text-sm">
                {(gaps.error as Error).message}
              </p>
            ) : (gaps.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Score some jobs to see what you keep lacking.
              </p>
            ) : (
              (gaps.data ?? []).map((row) => (
                <div key={row.skill} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm">{row.skill}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {row.n_jobs} {row.n_jobs === 1 ? "job" : "jobs"}
                  </span>
                </div>
              ))
            )}
            <Button
              className="mt-1 w-fit rounded-full"
              size="sm"
              variant="secondary"
              onClick={() => onOpenTab("gaps")}
            >
              Gaps & growth <ArrowRight aria-hidden="true" />
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick wins from your Career KB</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {buildAreas.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : buildAreas.error ? (
              <p role="alert" className="text-destructive text-sm">
                {(buildAreas.error as Error).message}
              </p>
            ) : quickWins.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No in-demand skills are sitting unused in your Career KB right now.
              </p>
            ) : (
              quickWins.map((row) => (
                <div key={row.skill} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm">{row.skill}</span>
                  <span className="text-primary shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs">
                    in your KB
                  </span>
                </div>
              ))
            )}
            <Button
              className="mt-1 w-fit rounded-full"
              size="sm"
              variant="secondary"
              onClick={() => onOpenTab("gaps")}
            >
              See all build areas <ArrowRight aria-hidden="true" />
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <AutofillCoverageCard />
        <AgentPipelineCard />
      </div>
    </div>
  );
}
