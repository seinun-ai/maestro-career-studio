"use client";

import { useQuery } from "@tanstack/react-query";

import { useExploreOverview, type OverviewFilters } from "@/components/explore/explore-overview";
import { humanizeEnum } from "@/components/job-extracted-fields";
import { LoadErrorState } from "@/components/load-error-state";
import { useRoleLabel } from "@/components/role-category-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SegmentedBar, type SegmentTone } from "@/components/visual";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { formatShortDate } from "@/lib/format-date";
import { APPROX, formatPay } from "@/lib/money";
import { isLoadFailure } from "@/lib/query-state";
import { skillName } from "@/lib/skill-name";
import type { BuildAreaRow, ExploreOverview, ExplorePayByRole, TopSkillsResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

/** No filter: Jobs you saved is every saved job. Market in detail filters its own copy. */
const NO_FILTERS: OverviewFilters = {
  role_category: null,
  level: null,
  employment_type: null,
  country: null,
  salary_currency: null,
};
const TOP_SKILLS = 5;
const TOP_GAPS = 5;

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Pay already in your home currency (`pay_by_role`): its narrow symbol, and "≈" when any of it was converted. */
const homePay = (min: number | null, max: number | null, home: string, converted: boolean) => {
  const text = formatPay({ min, max, currency: home, period: null }, { home })?.primary;
  return text ? `${converted ? APPROX : ""}${text}` : "—";
};

/** The chips under the pay bars: what was converted and on which day's rate, the roles hidden for having too
 * few jobs, and the jobs left out for having no rate. Numbers from the payload, worded here. */
function payNotes(pay: ExplorePayByRole): string[] {
  const notes: string[] = [];
  if (pay.converted_count > 0 && pay.rate_date) {
    const parts = pay.posted_currencies.map((c) => `${c.count} ${c.key}`);
    const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
    notes.push(
      `${list} ${pay.converted_count === 1 ? "job" : "jobs"} converted, ECB rate of ${formatShortDate(pay.rate_date)}`,
    );
  }
  if (pay.hidden_roles.length > 0) {
    notes.push(`${count(pay.hidden_roles.length, "role", "roles")} hidden: under ${pay.min_jobs} jobs`);
  }
  if (pay.unconverted > 0) {
    notes.push(`${count(pay.unconverted, "job", "jobs")} left out: no exchange rate`);
  }
  return notes;
}

/** A work mode is not a status, so its parts take chart series, fixed per mode (colour follows the mode, never its
 * rank). Any other stated mode folds into Other; a job that states none is Not stated. */
const MODE_TONE: Record<string, SegmentTone> = { hybrid: "chart-1", on_site: "chart-2", remote: "chart-3" };
const NOT_STATED = new Set(["unstated", "unknown"]);

function workModeParts(rows: ExploreOverview["work_mode"]) {
  const known = rows
    .filter((r) => MODE_TONE[r.key])
    .map((r) => ({ key: r.key, label: humanizeEnum(r.key) ?? r.key, count: r.count, tone: MODE_TONE[r.key] }));
  const other = rows.filter((r) => !MODE_TONE[r.key] && !NOT_STATED.has(r.key)).reduce((n, r) => n + r.count, 0);
  const unstated = rows.filter((r) => NOT_STATED.has(r.key)).reduce((n, r) => n + r.count, 0);
  return [
    ...known.sort((a, b) => b.count - a.count),
    ...(other > 0 ? [{ key: "other", label: "Other", count: other, tone: "chart-4" as const }] : []),
    ...(unstated > 0 ? [{ key: "unstated", label: "Not stated", count: unstated, tone: "empty" as const }] : []),
  ];
}

function PayByRoleCard({ overview, className }: { overview: ExploreOverview; className?: string }) {
  const label = useRoleLabel();
  const pay = overview.pay_by_role;
  const top = Math.max(0, ...pay.roles.map((r) => r.avg_max ?? 0));
  const at = (value: number) => (top > 0 ? (value / top) * 100 : 0);
  const notes = payNotes(pay);
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <CardTitle>Yearly pay by role</CardTitle>
          <span className="text-muted-foreground text-body-small">
            {overview.meta.jobs_with_salary} of {overview.meta.total_jobs} list pay
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {pay.roles.length === 0 ? (
          <p className="text-muted-foreground text-body-medium">
            {pay.hidden_roles.length > 0
              ? `No role has ${pay.min_jobs} jobs that list pay yet.`
              : "No pay data yet. Most jobs don't list pay."}
          </p>
        ) : (
          <ul className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3">
            {pay.roles.map((r) => {
              const name = label(r.role_category);
              const high = r.avg_max ?? 0;
              const low = r.avg_min ?? high;
              return (
                <li key={r.role_category} className="col-span-3 grid grid-cols-subgrid items-center">
                  <span className="truncate text-title-small" title={name}>{name}</span>
                  <span aria-hidden="true" className="relative h-3 rounded-full bg-surface-container">
                    <span
                      className="absolute inset-y-0 rounded-full bg-chart-1"
                      style={{ left: `${at(low)}%`, width: `${at(high) - at(low)}%`, minWidth: 8 }}
                    />
                  </span>
                  <span className="text-right tabular-nums">
                    {homePay(r.avg_min, r.avg_max, pay.currency, r.converted_count > 0)}{" "}
                    <span className="text-muted-foreground text-body-small">{count(r.n, "job", "jobs")}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {notes.length > 0 ? (
          <ul aria-label="How pay is counted" className="flex flex-wrap gap-2">
            {notes.map((note) => (
              <li key={note} className="rounded-full bg-surface-container px-2.5 py-1 text-body-small text-muted-foreground">
                {note}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function WorkModeCard({ overview, className }: { overview: ExploreOverview; className?: string }) {
  const parts = workModeParts(overview.work_mode);
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader>
        <CardTitle>Work mode</CardTitle>
      </CardHeader>
      <CardContent>
        {parts.length === 0 ? (
          <p className="text-muted-foreground text-body-medium">No data yet.</p>
        ) : (
          <SegmentedBar name="Work mode" parts={parts} className="gap-3" />
        )}
      </CardContent>
    </Card>
  );
}

/** One counted row: the name, a bar on the card's own scale, the count. The bar is decoration; the count is read. */
function CountRow({ name, n, max, tag }: { name: string; n: number; max: number; tag?: string }) {
  return (
    <li className="col-span-3 grid grid-cols-subgrid items-center">
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate" title={name}>{name}</span>
        {tag ? (
          <span className="shrink-0 rounded-full bg-surface-container px-2 text-label-medium text-muted-foreground">{tag}</span>
        ) : null}
      </span>
      <span aria-hidden="true" className="h-2 overflow-hidden rounded-r-corner-xs bg-surface-container">
        <span className="block h-full rounded-r-corner-xs bg-chart-1" style={{ width: `${max > 0 ? (n / max) * 100 : 0}%` }} />
      </span>
      <span className="text-right text-body-small text-muted-foreground tabular-nums">{count(n, "job", "jobs")}</span>
    </li>
  );
}

function SkillsCard({ onSeeAll, className }: { onSeeAll: () => void; className?: string }) {
  const query = useQuery({
    queryKey: ["explore", "top-skills", "teaser"],
    queryFn: () => apiFetch<TopSkillsResponse>(`/api/explore/top-skills?limit=${TOP_SKILLS}`),
  });
  const data = query.data;
  // A skill seen in one job is not a pattern yet (canvas: it leaves Analytics). Ranked across both tiers.
  const shown = data
    ? [...data.top, ...data.rest]
        .sort((a, b) => a.rank - b.rank)
        .filter((row) => row.n > 1)
        .slice(0, TOP_SKILLS)
    : [];
  const rest = data ? data.meta.total_skills - shown.length : 0;
  const max = Math.max(0, ...shown.map((row) => row.n));
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader>
        <CardTitle>Skills jobs ask for</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoadFailure(query) ? (
          <LoadErrorState
            className="py-6"
            title="Couldn't load the skills jobs ask for."
            detail={loadErrorDetail(query.error)}
            retrying={query.isFetching}
            onRetry={() => void query.refetch()}
          />
        ) : query.isLoading || !data ? (
          <Skeleton className="h-28 w-full" />
        ) : shown.length === 0 ? (
          <p className="text-muted-foreground text-body-medium">No skill comes up in more than one job yet.</p>
        ) : (
          <>
            <ol aria-label="Skills jobs ask for" className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] gap-x-3 gap-y-2.5">
              {shown.map((row) => (
                <CountRow key={`${row.skill_name}-${row.skill_category}`} name={skillName(row.skill_name)} n={row.n} max={max} />
              ))}
            </ol>
            {rest > 0 ? (
              <Button className="w-fit" size="sm" variant="ghost" onClick={onSeeAll}>
                See {count(rest, "more skill", "more skills")}
              </Button>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function GapsCard({ onSeeAll, className }: { onSeeAll: () => void; className?: string }) {
  const areas = useQuery({
    queryKey: ["explore", "build-areas", "teaser"],
    queryFn: () => apiFetch<BuildAreaRow[]>("/api/explore/build-areas?limit=20"),
  });
  // A wording-only row moves no score (its n_jobs is 0), so it is not a gap to close. Written "not wording" so a
  // backend that predates the tier field shows its rows instead of an empty card.
  const rows = (areas.data ?? []).filter((row) => row.tier !== "wording").slice(0, TOP_GAPS);
  const max = Math.max(0, ...rows.map((row) => row.n_jobs));
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader>
        <CardTitle>Most common gaps</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoadFailure(areas) ? (
          <LoadErrorState
            className="py-6"
            title="Couldn't load your most common gaps."
            detail={loadErrorDetail(areas.error)}
            retrying={areas.isFetching}
            onRetry={() => void areas.refetch()}
          />
        ) : areas.isLoading ? (
          <Skeleton className="h-28 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground text-body-medium">Score a few jobs to see which skills come up most.</p>
        ) : (
          <ol aria-label="Most common gaps" className="grid grid-cols-[minmax(0,1fr)_minmax(0,6rem)_auto] gap-x-3 gap-y-2.5">
            {rows.map((row) => (
              <CountRow
                key={row.skill}
                name={skillName(row.skill)}
                n={row.n_jobs}
                max={max}
                // The career-history evidence rides on the row: the skill is in your history, just not on a resume.
                tag={row.status === "in_kb" ? "In your career history" : undefined}
              />
            ))}
          </ol>
        )}
        <Button className="w-fit" size="sm" variant="tonal" onClick={onSeeAll}>
          See all skill gaps
        </Button>
      </CardContent>
    </Card>
  );
}

/** Analytics' second section: the jobs you saved, unfiltered. Pay arrives in your home currency (D8), work mode as a
 * split bar, the skills jobs ask for and your most common gaps; each reads and fails on its own. */
export function JobsYouSaved({ onOpenGaps, onOpenMarket }: { onOpenGaps: () => void; onOpenMarket: () => void }) {
  const overview = useExploreOverview(NO_FILTERS);
  const o = overview.data;
  return (
    <section aria-labelledby="jobs-you-saved" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h2 id="jobs-you-saved" className="text-title-medium">Jobs you saved</h2>
        {o && o.meta.total_jobs > 0 ? (
          <span className="text-muted-foreground text-body-small">
            {count(o.meta.total_jobs, "job", "jobs")}
            {o.meta.since ? ` since ${formatShortDate(o.meta.since)}` : ""} · pay in {o.pay_by_role.currency}
          </span>
        ) : null}
      </div>
      {isLoadFailure(overview) ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load the jobs you saved."
          detail={loadErrorDetail(overview.error)}
          retrying={overview.isFetching}
          onRetry={() => void overview.refetch()}
        />
      ) : overview.isLoading || !o ? (
        <div className="flex flex-wrap gap-4">
          <Skeleton className="h-48 flex-[3_1_26rem]" />
          <Skeleton className="h-48 flex-[2_1_18rem]" />
        </div>
      ) : o.meta.total_jobs === 0 ? (
        <p className="text-muted-foreground text-body-medium">Save a few jobs to see what they ask for and pay.</p>
      ) : (
        <div className="flex flex-wrap gap-4">
          <PayByRoleCard overview={o} className="flex-[3_1_26rem]" />
          <WorkModeCard overview={o} className="flex-[2_1_18rem]" />
        </div>
      )}
      <div className="flex flex-wrap gap-4">
        <SkillsCard onSeeAll={onOpenMarket} className="flex-[1_1_22rem]" />
        <GapsCard onSeeAll={onOpenGaps} className="flex-[1_1_22rem]" />
      </div>
    </section>
  );
}
