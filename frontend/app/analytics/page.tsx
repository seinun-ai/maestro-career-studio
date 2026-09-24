"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { AnalyticsOverview } from "@/components/analytics/analytics-overview";
import { BaseSummaryCards } from "@/components/analytics/base-summary-cards";
import { GapTiersPanel } from "@/components/analytics/gap-tiers-panel";
import { AtsOverTimeChart } from "@/components/charts/ats-over-time-chart";
import { FitDistributionChart } from "@/components/charts/fit-distribution-chart";
import { HeatmapChart } from "@/components/charts/heatmap-chart";
import { RoleMixChart } from "@/components/charts/role-mix-chart";
import { TailoringLiftChart } from "@/components/charts/tailoring-lift-chart";
import {
  TopSkillsChart,
  type TopSkillsFilters,
} from "@/components/charts/top-skills-chart";
import { ExploreOverview } from "@/components/explore/explore-overview";
import { humanizeEnum } from "@/components/job-extracted-fields";
import { useRoleLabel } from "@/components/role-category-picker";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api";
import type { Job } from "@/lib/types";
import { PageHeader, PageShell } from "@/components/page-shell";

const ANY = "__any__";

/** A stored level or employment type in words (`full_time` → "Full-time"). */
const enumLabel = (value: string) => humanizeEnum(value) ?? value;
const TABS = ["overview", "market", "fit", "gaps"] as const;
type TabValue = (typeof TABS)[number];

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <AnalyticsContent />
    </Suspense>
  );
}

function AnalyticsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // The URL is the single source of truth for the active tab — deriving (not
  // seeding useState) keeps the UI in sync when only search params change,
  // e.g. clicking the sidebar "Analytics" link while on ?tab=gaps.
  const urlTab = searchParams.get("tab");
  const tab: TabValue = TABS.includes(urlTab as TabValue)
    ? (urlTab as TabValue)
    : "overview";
  const [roleCategory, setRoleCategory] = useState<string>(ANY);
  const [level, setLevel] = useState<string>(ANY);
  const [employmentType, setEmploymentType] = useState<string>(ANY);
  const [country, setCountry] = useState<string>(ANY);
  const [salaryCurrency, setSalaryCurrency] = useState<string>(ANY);

  const changeTab = (value: string | null) => {
    const next = TABS.includes(value as TabValue) ? (value as TabValue) : "overview";
    router.replace(
      next === "overview" ? "/analytics" : `/analytics?tab=${next}`,
      { scroll: false },
    );
  };

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
      if (job.country) countries.add(job.country);
      if (job.salary_currency) currencies.add(job.salary_currency);
    }
    return {
      roles: [...roles].sort(
        (a, b) => label(a).localeCompare(label(b)) || a.localeCompare(b),
      ),
      levels: [...levels].sort(),
      employment: [...employment].sort(),
      countries: [...countries].sort(),
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

  const filterRow = (
    <div className="flex flex-wrap items-end gap-3">
      {filterSelect(
        "role_category",
        "Role",
        roleCategory,
        setRoleCategory,
        options.roles,
        label,
      )}
      {filterSelect("level", "Level", level, setLevel, options.levels, enumLabel)}
      {filterSelect(
        "employment_type",
        "Employment type",
        employmentType,
        setEmploymentType,
        options.employment,
        enumLabel,
      )}
      {filterSelect("country", "Country", country, setCountry, options.countries)}
      {filterSelect(
        "salary_currency",
        "Currency",
        salaryCurrency,
        setSalaryCurrency,
        options.currencies,
      )}
    </div>
  );

  return (
    <PageShell>
      <PageHeader
        className="animate-fade-rise"
        title="Analytics"
        subtitle="How your job search is going."
      />

      <Tabs value={tab} onValueChange={changeTab} className="gap-5">
        <TabsList className="h-auto flex-wrap rounded-full bg-muted/70 p-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="market">Job market</TabsTrigger>
          <TabsTrigger value="fit">Resume fit</TabsTrigger>
          <TabsTrigger value="gaps">Skill gaps</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <AnalyticsOverview onOpenTab={changeTab} />
        </TabsContent>

        <TabsContent value="market" className="grid gap-4">
          {filterRow}
          <ExploreOverview filters={filters} />
          <div className="grid gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Top skills</CardTitle>
                <p className="text-muted-foreground text-sm font-normal">
                  Skills ranked by how many jobs ask for them.
                </p>
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
                <RoleMixChart />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="fit" className="grid gap-4">
          <BaseSummaryCards />
          {filterRow}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>ATS score over time</CardTitle>
                <p className="text-muted-foreground text-sm font-normal">
                  Weekly average ATS score (how an applicant tracking system
                  rates a resume for a job).
                </p>
              </CardHeader>
              <CardContent>
                <AtsOverTimeChart filters={filters} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Score gain from tailoring</CardTitle>
                <p className="text-muted-foreground text-sm font-normal">
                  Average ATS score before and after tailoring, by role.
                </p>
              </CardHeader>
              <CardContent>
                <TailoringLiftChart filters={filters} />
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>ATS scores by resume</CardTitle>
              </CardHeader>
              <CardContent>
                <FitDistributionChart />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="gaps" className="grid gap-4">
          {filterRow}
          <Card>
            <CardHeader>
              <CardTitle>Skill gaps</CardTitle>
              <p className="text-muted-foreground text-sm font-normal">
                Skills to learn, and skills to show better. Based on your
                best-scoring resume for each job.
              </p>
            </CardHeader>
            <CardContent>
              <GapTiersPanel filters={filters} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
