"use client";

import { useQuery } from "@tanstack/react-query";

import { humanizeEnum } from "@/components/job-extracted-fields";
import { LoadErrorState } from "@/components/load-error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { countryName, placeName } from "@/lib/place-name";
import { isLoadFailure } from "@/lib/query-state";
import type { ExploreCountRow, ExploreOverview } from "@/lib/types";
import { LowSampleCaption } from "@/components/explore/low-sample-hint";
import { useRoleLabel } from "@/components/role-category-picker";

export type OverviewFilters = {
  role_category?: string | null;
  level?: string | null;
  employment_type?: string | null;
  country?: string | null;
  salary_currency?: string | null;
};

function buildPath(filters: OverviewFilters): string {
  const p = new URLSearchParams();
  if (filters.role_category) p.set("role_category", filters.role_category);
  if (filters.level) p.set("level", filters.level);
  if (filters.employment_type)
    p.set("employment_type", filters.employment_type);
  if (filters.country) p.set("country", filters.country);
  if (filters.salary_currency)
    p.set("salary_currency", filters.salary_currency);
  const qs = p.toString();
  return `/api/explore/overview${qs ? `?${qs}` : ""}`;
}

/** The saved jobs' overview. Jobs you saved reads it with no filter, Market in detail with the fold's filters: with
 * none set the two share one cache entry. */
export function useExploreOverview(filters: OverviewFilters) {
  return useQuery({
    queryKey: ["explore-overview", filters],
    queryFn: () => apiFetch<ExploreOverview>(buildPath(filters)),
  });
}

function BarList({
  rows,
  empty,
}: {
  rows: { label: string; count: number }[];
  empty: string;
}) {
  if (rows.length === 0)
    return <p className="text-muted-foreground text-body-medium">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((r, i) => (
        // Two stored keys can share a word ("unstated", "unknown": Not stated).
        <div key={`${i}:${r.label}`} className="flex items-center gap-2.5">
          <span
            className="text-foreground min-w-0 flex-shrink-0 basis-40 truncate text-body-medium"
            title={r.label}
          >
            {r.label}
          </span>
          <span className="bg-muted h-2 flex-1 overflow-hidden rounded-full">
            <span
              className="bg-primary block h-full rounded-full"
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </span>
          <span className="text-muted-foreground w-7 text-right text-body-small">
            {r.count}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Location keys are a state, else a city, else a country: "CA" read as Canada or California. */
const toPlaceBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({ label: placeName(r.key), count: r.count }));
/** Country keys are ISO codes; "unknown" is a job that names no one country. */
const toCountryBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({
    label: r.key === "unknown" ? "Not stated" : countryName(r.key),
    count: r.count,
  }));
/** Bars whose keys are stored enums (`senior`, `no_sponsorship`): words, never the key. */
const toEnumBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({ label: humanizeEnum(r.key) ?? r.key, count: r.count }));

/**
 * Market in detail: the saved jobs by role, level, place, country and work authorization, under the fold's own
 * filter row. Work authorization is the jobs' stated sponsorship terms; there is no payload per country you apply
 * in, so the Country filter is how it reads for one country.
 */
export function MarketDetail({ filters }: { filters: OverviewFilters }) {
  const q = useExploreOverview(filters);
  const label = useRoleLabel();

  // Before the loading gate: a retry with no data is "pending" again, and the
  // skeleton would unmount the focused Try again.
  if (isLoadFailure(q))
    return (
      <LoadErrorState
        className="py-8"
        title="Couldn't load job market data."
        detail={loadErrorDetail(q.error)}
        retrying={q.isFetching}
        onRetry={() => void q.refetch()}
      />
    );
  if (q.isLoading || !q.data)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  const o = q.data;
  const total = o.meta.total_jobs;
  if (total === 0)
    return (
      <p className="text-muted-foreground text-body-medium">
        Add a few jobs to see this.
      </p>
    );

  return (
    <div className="flex flex-col gap-4">
      <LowSampleCaption n={total} lowSample={total < 5} unit="jobs" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Roles</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={o.role_mix.map((row) => ({
                label: label(row.key),
                count: row.count,
              }))}
              empty="No data"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Level</CardTitle>
            <p className="text-muted-foreground text-body-small">
              Sorted from each job description into one of these levels.
            </p>
          </CardHeader>
          <CardContent>
            <BarList rows={toEnumBars(o.level_breakdown)} empty="No data" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top locations</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={toPlaceBars(o.locations)}
              empty="No locations found"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Countries</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={toCountryBars(o.countries ?? [])}
              empty="No countries found"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Work authorization</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList rows={toEnumBars(o.work_auth.sponsorship)} empty="No data" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
