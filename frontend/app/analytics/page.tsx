"use client";

import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { AgentPipelineFold } from "@/components/analytics/agent-pipeline-card";
import { ApplicationsFunnel } from "@/components/analytics/applications-funnel";
import { BaseSummaryCards } from "@/components/analytics/base-summary-cards";
import { ByResumeCard } from "@/components/analytics/by-resume-card";
import { EachWeekChart } from "@/components/analytics/each-week-chart";
import { GapTiersPanel } from "@/components/analytics/gap-tiers-panel";
import { HowCounted } from "@/components/analytics/how-counted";
import { JobsYouSaved } from "@/components/analytics/jobs-you-saved";
import { PeriodToggle } from "@/components/analytics/period-toggle";
import { SearchTiles } from "@/components/analytics/search-tiles";
import { AtsOverTimeChart } from "@/components/charts/ats-over-time-chart";
import { FitDistributionChart } from "@/components/charts/fit-distribution-chart";
import { HeatmapChart } from "@/components/charts/heatmap-chart";
import { RoleMixChart } from "@/components/charts/role-mix-chart";
import { TailoringLiftChart } from "@/components/charts/tailoring-lift-chart";
import {
  TopSkillsChart,
  type TopSkillsFilters,
} from "@/components/charts/top-skills-chart";
import { MarketDetail } from "@/components/explore/explore-overview";
import { humanizeEnum } from "@/components/job-extracted-fields";
import { LoadErrorState } from "@/components/load-error-state";
import { PageHeader, PageShell } from "@/components/page-shell";
import { useRoleLabel } from "@/components/role-category-picker";
import { SourceToggle, type SourceFilter } from "@/components/source-toggle";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Fold } from "@/components/ui/fold";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { ATS_SCORE_LEAD_ALL_JOBS } from "@/lib/ats-words";
import { loadErrorDetail } from "@/lib/error-text";
import { countryName } from "@/lib/place-name";
import { isLoadFailure } from "@/lib/query-state";
import { DEFAULT_PERIOD, summaryKey, summaryPath, type Period } from "@/lib/search-summary";
import type { Job, SearchSummary } from "@/lib/types";

const ANY = "__any__";

/** A stored level or employment type in words (`full_time` → "Full-time"). */
const enumLabel = (value: string) => humanizeEnum(value) ?? value;
/** The folds that carry the job filters. Each prefixes its controls' ids: every fold stays mounted, hidden. */
type FilterPanel = "fit" | "gaps" | "market";

/**
 * Analytics, one page (design refresh Task 5.2, owner decisions D1, D6, D7, D8). The period and the source scope the
 * applications: the Lead (where they went) and the Also tier (four tiles, each week, by resume) read one search
 * summary. Jobs you saved reads every saved job. The detail is folded, each fold under its own row of job filters.
 */
export default function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [source, setSource] = useState<SourceFilter>("all");
  const [gapsOpen, setGapsOpen] = useState(false);
  const [marketOpen, setMarketOpen] = useState(false);
  const [roleCategory, setRoleCategory] = useState<string>(ANY);
  const [level, setLevel] = useState<string>(ANY);
  const [employmentType, setEmploymentType] = useState<string>(ANY);
  const [country, setCountry] = useState<string>(ANY);
  const [salaryCurrency, setSalaryCurrency] = useState<string>(ANY);

  const summary = useQuery({
    queryKey: summaryKey(period, source),
    queryFn: () => apiFetch<SearchSummary>(summaryPath(period, source)),
    // A new period or source holds the last answer, dimmed, until its own arrives: no skeleton flash, and the
    // counts roll from the old values to the new.
    placeholderData: keepPreviousData,
  });

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => apiFetch<Job[]>("/api/jobs"),
  });
  const label = useRoleLabel();

  const options = useMemo(() => {
    const roles = new Set<string>();
    const levels = new Set<string>();
    const employment = new Set<string>();
    const countries = new Set<string>();
    const currencies = new Set<string>();
    for (const job of jobs.data ?? []) {
      if (job.role_category) roles.add(job.role_category);
      if (job.level) levels.add(job.level);
      if (job.employment_type) employment.add(job.employment_type);
      if (job.country_code) countries.add(job.country_code);
      if (job.salary_currency) currencies.add(job.salary_currency);
    }
    return {
      roles: [...roles].sort(
        (a, b) => label(a).localeCompare(label(b)) || a.localeCompare(b),
      ),
      levels: [...levels].sort(),
      employment: [...employment].sort(),
      countries: [...countries].sort((a, b) => countryName(a).localeCompare(countryName(b))),
      currencies: [...currencies].sort(),
    };
  }, [jobs.data, label]);

  const filters: TopSkillsFilters = {
    role_category: roleCategory === ANY ? null : roleCategory,
    level: level === ANY ? null : level,
    employment_type: employmentType === ANY ? null : employmentType,
    country: country === ANY ? null : country,
    salary_currency: salaryCurrency === ANY ? null : salaryCurrency,
  };

  const filterSelect = (
    id: string,
    fieldLabel: string,
    value: string,
    onChange: (v: string) => void,
    items: string[],
    format: (v: string) => string = (v) => v,
  ) => (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{fieldLabel}</Label>
      <Select value={value} onValueChange={(v) => onChange(v ?? ANY)}>
        <SelectTrigger id={id} className="w-44">
          <SelectValue>
            {(v) => (v === ANY ? "Any" : format(String(v ?? "")))}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {items.map((it) => (
            <SelectItem key={it} value={it}>
              {format(it)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  // Three folds show this row and every fold stays mounted, so each one prefixes the control ids with its own
  // name: a bare `role_category` would be three ids on one page, and a label's `htmlFor` would resolve to the
  // first (hidden) fold's trigger and leave the visible ones unnamed.
  const filterRow = (panel: FilterPanel) => (
    <div className="flex flex-wrap items-end gap-3">
      {filterSelect(
        `${panel}-role_category`,
        "Role",
        roleCategory,
        setRoleCategory,
        options.roles,
        label,
      )}
      {filterSelect(`${panel}-level`, "Level", level, setLevel, options.levels, enumLabel)}
      {filterSelect(
        `${panel}-employment_type`,
        "Employment type",
        employmentType,
        setEmploymentType,
        options.employment,
        enumLabel,
      )}
      {filterSelect(
        `${panel}-country`,
        "Country",
        country,
        setCountry,
        options.countries,
        countryName,
      )}
      {filterSelect(
        `${panel}-salary_currency`,
        "Currency",
        salaryCurrency,
        setSalaryCurrency,
        options.currencies,
      )}
    </div>
  );

  const openGaps = () => {
    setGapsOpen(true);
    // After the fold opens: the panel is `hidden` until this render lands.
    requestAnimationFrame(() => document.getElementById("skill-gaps")?.scrollIntoView({ block: "start" }));
  };
  const openMarket = () => {
    setMarketOpen(true);
    requestAnimationFrame(() => document.getElementById("market-in-detail")?.scrollIntoView({ block: "start" }));
  };

  return (
    <PageShell>
      <PageHeader
        title="Analytics"
        actions={
          <>
            <PeriodToggle value={period} onChange={setPeriod} />
            <SourceToggle value={source} onChange={setSource} />
          </>
        }
      />

      {/* The failure first: a retry with no data is loading again, and the skeleton would unmount the focused
          Try again. */}
      {isLoadFailure(summary) ? (
        <LoadErrorState
          className="py-8"
          title="Couldn't load where your applications went."
          detail={loadErrorDetail(summary.error)}
          retrying={summary.isFetching}
          onRetry={() => void summary.refetch()}
        />
      ) : summary.isLoading || !summary.data ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-72 w-full rounded-corner-lg" />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-28 w-full" />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4" data-pending={summary.isPlaceholderData ? "true" : undefined}>
          <ApplicationsFunnel summary={summary.data} />
          <SearchTiles summary={summary.data} />
          <div className="flex flex-wrap gap-4">
            <EachWeekChart summary={summary.data} className="min-w-0 flex-[3_1_26rem]" />
            <ByResumeCard summary={summary.data} className="flex-[2_1_20rem]" />
          </div>
        </div>
      )}

      <JobsYouSaved onOpenGaps={openGaps} onOpenMarket={openMarket} />

      <div className="flex flex-col gap-2">
        <Fold title="Match scores in detail" summary="Over time, by resume, by role">
          <div className="grid gap-4">
            {/* "ATS score" spelled out once, above the fold's first card. */}
            <p className="text-muted-foreground max-w-[60ch] text-body-medium">{ATS_SCORE_LEAD_ALL_JOBS}</p>
            <BaseSummaryCards />
            {filterRow("fit")}
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Match score over time</CardTitle>
                </CardHeader>
                <CardContent>
                  <AtsOverTimeChart filters={filters} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Score gain from tailoring, by role</CardTitle>
                </CardHeader>
                <CardContent>
                  <TailoringLiftChart filters={filters} />
                </CardContent>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Match scores by resume</CardTitle>
                </CardHeader>
                <CardContent>
                  <FitDistributionChart />
                </CardContent>
              </Card>
            </div>
          </div>
        </Fold>

        <div id="skill-gaps" className="scroll-mt-4">
          <Fold
            title="Skill gaps"
            summary="To learn and to show, from your best resume per job"
            open={gapsOpen}
            onOpenChange={setGapsOpen}
          >
            <div className="grid gap-4">
              {filterRow("gaps")}
              <GapTiersPanel filters={filters} />
            </div>
          </Fold>
        </div>

        <div id="market-in-detail" className="scroll-mt-4">
          <Fold
            title="Market in detail"
            summary="Level, places, work authorization, skills by role"
            open={marketOpen}
            onOpenChange={setMarketOpen}
          >
            <div className="grid gap-4">
              {filterRow("market")}
              <MarketDetail filters={filters} />
              <Card>
                <CardHeader>
                  <CardTitle>Every skill jobs ask for</CardTitle>
                </CardHeader>
                <CardContent>
                  <TopSkillsChart filters={filters} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Skills by role</CardTitle>
                </CardHeader>
                <CardContent>
                  <HeatmapChart filters={filters} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Roles over time</CardTitle>
                </CardHeader>
                <CardContent>
                  <RoleMixChart filters={filters} />
                </CardContent>
              </Card>
            </div>
          </Fold>
        </div>

        <AgentPipelineFold />

        <Fold title="How these are counted" summary="Definitions and sample sizes">
          <HowCounted summary={summary.data} />
        </Fold>
      </div>
    </PageShell>
  );
}
