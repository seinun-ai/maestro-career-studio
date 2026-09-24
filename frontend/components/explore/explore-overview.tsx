"use client";

import { useQuery } from "@tanstack/react-query";
import { StatTile } from "@/components/analytics/stat-tile";

import { formatSalary, humanizeEnum } from "@/components/job-extracted-fields";
import { LoadErrorState } from "@/components/load-error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { formatShortDate } from "@/lib/format-date";
import { countryName, placeName } from "@/lib/place-name";
import { isLoadFailure } from "@/lib/query-state";
import { skillName } from "@/lib/skill-name";
import type { ExploreCountRow, ExploreOverview } from "@/lib/types";
import { LowSampleCaption } from "@/components/explore/low-sample-hint";
import { useRoleLabel } from "@/components/role-category-picker";

type Filters = {
  role_category?: string | null;
  level?: string | null;
  employment_type?: string | null;
  country?: string | null;
  salary_currency?: string | null;
};

function buildPath(filters: Filters): string {
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

const pct = (n: number, total: number) =>
  total > 0 ? Math.round((n / total) * 100) : 0;

/**
 * A signal in the words the charts below use. The server names the top location by its key ("CA") and
 * the top skill as stored ("python"), `explore_overview.candidate_signals`; this page has the tables
 * that say them (placeName, skillName), so "Most common location: California" beside "California".
 */
function signalTitle(title: string, o: ExploreOverview): string {
  const place = o.locations[0]?.key;
  const skill = o.top_required_skills[0]?.skill_name;
  if (place && title.startsWith("Most common location: ")) {
    return title.replace(`: ${place} (`, `: ${placeName(place)} (`);
  }
  if (skill && title.startsWith("Most required skill: ")) {
    return title.replace(`: ${skill} (`, `: ${skillName(skill)} (`);
  }
  return title;
}
/** Pay the way the job header shows it ("$171K–$214K", "£70K–£90K"): one money format. */
const payRange = (min: number | null, max: number | null, currency?: string | null) =>
  formatSalary(min, max, null, currency ?? null) ?? "—";


function BarList({
  rows,
  empty,
}: {
  rows: { label: string; count: number }[];
  empty: string;
}) {
  if (rows.length === 0)
    return <p className="text-muted-foreground text-sm">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((r, i) => (
        // Two stored keys can share a word ("unstated", "unknown": Not stated).
        <div key={`${i}:${r.label}`} className="flex items-center gap-2.5">
          <span
            className="text-foreground min-w-0 flex-shrink-0 basis-40 truncate text-sm"
            title={r.label}
          >
            {r.label}
          </span>
          <span className="bg-muted h-2 flex-1 overflow-hidden rounded">
            <span
              className="bg-primary/70 block h-full rounded"
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </span>
          <span className="text-muted-foreground w-7 text-right text-xs">
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
const toCountryBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({ label: countryName(r.key), count: r.count }));
/** Bars whose keys are stored enums (`onsite`, `stem_opt_ok`): words, never the key. */
const toEnumBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({ label: humanizeEnum(r.key) ?? r.key, count: r.count }));

export function ExploreOverview({ filters }: { filters: Filters }) {
  const q = useQuery({
    queryKey: ["explore-overview", filters],
    queryFn: () => apiFetch<ExploreOverview>(buildPath(filters)),
  });
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
      <p className="text-muted-foreground text-sm">
        Add a few jobs to see this.
      </p>
    );

  const onsite = o.work_mode.find((r) => r.key === "onsite")?.count ?? 0;
  const optAccept =
    (o.work_auth.opt.find((r) => r.key === "yes")?.count ?? 0) +
    (o.work_auth.opt.find((r) => r.key === "stem_opt_ok")?.count ?? 0);
  const salaryAvg =
    !o.meta.salary_mixed_currencies &&
    o.meta.salary_year_avg_min != null &&
    o.meta.salary_year_avg_max != null
      ? payRange(o.meta.salary_year_avg_min, o.meta.salary_year_avg_max, o.meta.salary_year_currency)
      : o.meta.salary_mixed_currencies
        ? "Mixed currencies"
        : "—";
  const salarySub = o.meta.salary_mixed_currencies
    ? "Filter by currency"
    : o.meta.jobs_with_salary
      ? `${o.meta.jobs_with_salary} list pay · ${o.meta.jobs_without_salary} don't`
      : "Yearly pay only";

  return (
    <div className="flex flex-col gap-4">
      <LowSampleCaption n={total} lowSample={total < 5} unit="jobs" />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile
          label="Jobs"
          value={String(total)}
          sub={o.meta.since ? `Since ${formatShortDate(o.meta.since)}` : undefined}
        />
        <StatTile
          label="Roles"
          value={String(o.meta.role_category_count)}
        />
        <StatTile
          label="On-site"
          value={`${pct(onsite, total)}%`}
          sub={`${onsite} of ${total}`}
        />
        <StatTile
          label="Average yearly pay"
          value={salaryAvg}
          sub={salarySub}
        />
        <StatTile
          // OPT spelled out where the tab first shows it.
          label="OPT (US student work permit)"
          value={`${pct(optAccept, total)}%`}
          // The one place the tab says it (the server's OPT signal is gone), with STEM OPT explained.
          sub={`${optAccept} of ${total} accept OPT or STEM OPT (24 more months for science and tech degrees)`}
        />
      </div>

      {o.signals.length > 0 && (
        <div className="flex flex-col gap-2">
          {o.signals.map((s, i) => (
            <div key={i} className="bg-muted/40 rounded-md px-3 py-2">
              <p className="text-foreground text-sm font-medium">{signalTitle(s.title, o)}</p>
              <p className="text-muted-foreground mt-0.5 text-xs">{s.detail}</p>
            </div>
          ))}
        </div>
      )}

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
            <CardTitle>Top required skills</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={o.top_required_skills.map((s) => ({
                label: skillName(s.skill_name),
                count: s.n,
              }))}
              empty="No required skills found"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Work mode</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList rows={toEnumBars(o.work_mode)} empty="No data" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Level</CardTitle>
            <p className="text-muted-foreground text-xs font-normal">
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
            <CardTitle>OPT and sponsorship</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div>
              <p className="text-muted-foreground mb-1 text-xs">OPT accepted</p>
              <BarList rows={toEnumBars(o.work_auth.opt)} empty="No data" />
            </div>
            <div>
              <p className="text-muted-foreground mb-1 text-xs">
                Work authorization
              </p>
              <BarList rows={toEnumBars(o.work_auth.sponsorship)} empty="No data" />
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Yearly pay by role</CardTitle>
            {o.meta.salary_mixed_currencies ? (
              <p className="text-muted-foreground text-xs font-normal">
                Shown per currency, since jobs use more than one.
              </p>
            ) : null}
          </CardHeader>
          <CardContent>
            {o.salary_by_role.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No pay data yet. Most jobs don&apos;t list pay.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
                {o.salary_by_role.map((r) => (
                  <div
                    key={`${r.role_category}:${r.currency ?? "unknown"}`}
                    className="bg-muted/40 rounded-md p-3"
                  >
                    <p className="text-muted-foreground text-xs">
                      {label(r.role_category)}
                      {r.currency ? ` · ${r.currency}` : ""}
                    </p>
                    <p className="text-foreground text-base font-medium">
                      {payRange(r.avg_min, r.avg_max, r.currency)}
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {r.n} {r.n === 1 ? "job" : "jobs"} with pay listed
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
