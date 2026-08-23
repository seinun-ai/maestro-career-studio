"use client";

import { useQuery } from "@tanstack/react-query";
import { StatTile } from "@/components/analytics/stat-tile";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import type { ExploreCountRow, ExploreOverview } from "@/lib/types";
import { LowSampleCaption } from "@/components/explore/low-sample-hint";

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
const fmtK = (n: number | null, currency?: string | null) => {
  if (n == null) return "—";
  const code = currency || "";
  const amount = `${Math.round(n / 1000)}k`;
  return code ? `${code} ${amount}` : `$${amount}`;
};


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
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2.5">
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

const toBars = (rows: ExploreCountRow[]) =>
  rows.map((r) => ({ label: r.key, count: r.count }));

export function ExploreOverview({ filters }: { filters: Filters }) {
  const q = useQuery({
    queryKey: ["explore-overview", filters],
    queryFn: () => apiFetch<ExploreOverview>(buildPath(filters)),
  });

  if (q.isLoading)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  if (q.isError || !q.data)
    return <p className="text-destructive text-sm">Failed to load overview.</p>;

  const o = q.data;
  const total = o.meta.total_jobs;
  if (total === 0)
    return (
      <p className="text-muted-foreground text-sm">
        No job descriptions yet. Capture a few to see the dashboard.
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
      ? `${fmtK(o.meta.salary_year_avg_min, o.meta.salary_year_currency)}–${fmtK(o.meta.salary_year_avg_max, o.meta.salary_year_currency)}`
      : o.meta.salary_mixed_currencies
        ? "mixed"
        : "—";
  const salarySub = o.meta.salary_mixed_currencies
    ? "filter by currency"
    : o.meta.jobs_with_salary
      ? `${o.meta.jobs_with_salary} disclosed · ${o.meta.jobs_without_salary} omit pay`
      : "year only · omit is normal";

  return (
    <div className="flex flex-col gap-4">
      <LowSampleCaption n={total} lowSample={total < 5} unit="jobs" />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile
          label="total JDs"
          value={String(total)}
          sub={o.meta.since ? `since ${o.meta.since.slice(0, 10)}` : undefined}
        />
        <StatTile
          label="role categories"
          value={String(o.meta.role_category_count)}
        />
        <StatTile
          label="onsite"
          value={`${pct(onsite, total)}%`}
          sub={`${onsite} of ${total}`}
        />
        <StatTile
          label="avg yearly salary"
          value={salaryAvg}
          sub={salarySub}
        />
        <StatTile
          label="OPT accepted"
          value={`${pct(optAccept, total)}%`}
          sub={`${optAccept} of ${total}`}
        />
      </div>

      {o.signals.length > 0 && (
        <div className="flex flex-col gap-2">
          {o.signals.map((s, i) => (
            <div key={i} className="bg-muted/40 rounded-md px-3 py-2">
              <p className="text-foreground text-sm font-medium">{s.title}</p>
              <p className="text-muted-foreground mt-0.5 text-xs">{s.detail}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Role category mix</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList rows={toBars(o.role_mix)} empty="No data" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top required skills</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={o.top_required_skills.map((s) => ({
                label: s.skill_name,
                count: s.n,
              }))}
              empty="No required skills tagged"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Work mode</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList rows={toBars(o.work_mode)} empty="No data" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Level</CardTitle>
            <p className="text-muted-foreground text-xs font-normal">
              Free text, so values may be inconsistent.
            </p>
          </CardHeader>
          <CardContent>
            <BarList rows={toBars(o.level_breakdown)} empty="No data" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top locations</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={toBars(o.locations)}
              empty="No locations extracted"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Countries</CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              rows={toBars(o.countries ?? [])}
              empty="No countries extracted"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>OPT &amp; sponsorship</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div>
              <p className="text-muted-foreground mb-1 text-xs">OPT accepted</p>
              <BarList rows={toBars(o.work_auth.opt)} empty="No data" />
            </div>
            <div>
              <p className="text-muted-foreground mb-1 text-xs">
                Work authorization
              </p>
              <BarList rows={toBars(o.work_auth.sponsorship)} empty="No data" />
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              Salary by track (yearly)
            </CardTitle>
            {o.meta.salary_mixed_currencies ? (
              <p className="text-muted-foreground text-xs font-normal">
                Multiple currencies in scope, so rows are per currency rather than blended.
              </p>
            ) : null}
          </CardHeader>
          <CardContent>
            {o.salary_by_role.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No pay numbers yet. Most postings omit salary, and that is normal.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
                {o.salary_by_role.map((r) => (
                  <div
                    key={`${r.role_category}:${r.currency ?? "unknown"}`}
                    className="bg-muted/40 rounded-md p-3"
                  >
                    <p className="text-muted-foreground text-xs">
                      {r.role_category}
                      {r.currency ? ` · ${r.currency}` : ""}
                    </p>
                    <p className="text-foreground text-base font-medium">
                      {fmtK(r.avg_min, r.currency)}–{fmtK(r.avg_max, r.currency)}
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {r.n} disclosed
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
