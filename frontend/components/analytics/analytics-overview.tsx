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
import { LoadErrorState } from "@/components/load-error-state";
import { apiFetch } from "@/lib/api";
import { errorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import { LowSampleBadge } from "@/components/explore/low-sample-hint";
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

      {/* The failure first: a retry with no data is loading again, and the
          skeleton would unmount the focused Try again. */}
      {isLoadFailure(activity) ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load your activity."
          detail={errorDetail(activity.error)}
          retrying={activity.isFetching}
          onRetry={() => void activity.refetch()}
        />
      ) : activity.isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile
            label="Applied · last 7 days"
            value={String(totals?.submitted_last7 ?? 0)}
            sub={`${totals?.submitted ?? 0} all time`}
          />
          <StatTile
            label="In progress"
            value={String(totals?.in_flight ?? 0)}
            sub="Applied, interviewing or offer"
          />
          <StatTile
            label="Reached interviews"
            value={
              totals?.interview_rate != null
                ? `${Math.round(totals.interview_rate * 100)}%`
                : "—"
            }
            sub={
              totals?.submitted
                ? `of ${totals.submitted} applications`
                : "No applications yet"
            }
          />
          <StatTile
            label="Average score gain"
            value={allLift ? `${allLift.avg_lift > 0 ? "+" : ""}${allLift.avg_lift}` : "—"}
            sub={
              allLift
                ? `points across ${allLift.n} tailored ${allLift.n === 1 ? "resume" : "resumes"}`
                : "Nothing tailored yet"
            }
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
            {isLoadFailure(gaps) ? (
              <LoadErrorState
                className="py-6"
                title="Couldn't load your most common gaps."
                detail={errorDetail(gaps.error)}
                retrying={gaps.isFetching}
                onRetry={() => void gaps.refetch()}
              />
            ) : gaps.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : (gaps.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Score a few jobs to see which skills come up most.
              </p>
            ) : (
              (gaps.data ?? []).map((row) => (
                <div key={row.skill} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm">{row.skill}</span>
                  <span className="text-muted-foreground flex shrink-0 items-center gap-1.5 text-xs">
                    {row.n_jobs} {row.n_jobs === 1 ? "job" : "jobs"}
                    <LowSampleBadge
                      n={row.n_jobs}
                      lowSample={row.low_sample}
                      unit="jobs"
                    />
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
              Skill gaps <ArrowRight aria-hidden="true" />
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick wins from your career history</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {isLoadFailure(buildAreas) ? (
              <LoadErrorState
                className="py-6"
                title="Couldn't load your quick wins."
                detail={errorDetail(buildAreas.error)}
                retrying={buildAreas.isFetching}
                onRetry={() => void buildAreas.refetch()}
              />
            ) : buildAreas.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : quickWins.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No unused skills in your career history match what jobs ask for.
              </p>
            ) : (
              quickWins.map((row) => (
                <div key={row.skill} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm">{row.skill}</span>
                  <span className="text-primary shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs">
                    In your career history
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
              See all skill gaps <ArrowRight aria-hidden="true" />
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
