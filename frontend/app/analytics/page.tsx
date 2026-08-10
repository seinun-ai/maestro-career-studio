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
      roles: [...roles].sort(),
      levels: [...levels].sort(),
      employment: [...employment].sort(),
      countries: [...countries].sort(),
      currencies: [...currencies].sort(),
    };
  }, [jobs.data]);

  const filters: TopSkillsFilters = {
    role_category: roleCategory === ANY ? null : roleCategory,
    level: level === ANY ? null : level,
    employment_type: employmentType === ANY ? null : employmentType,
    country: country === ANY ? null : country,
    salary_currency: salaryCurrency === ANY ? null : salaryCurrency,
  };

  const filterSelect = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    items: string[],
  ) => (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={(v) => onChange(v ?? ANY)}>
        <SelectTrigger id={id} className="w-44">
          <SelectValue>
            {(v) => (v === ANY ? "any" : String(v ?? ""))}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>any</SelectItem>
          {items.map((it) => (
            <SelectItem key={it} value={it}>
              {it}
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
        "Role category",
        roleCategory,
        setRoleCategory,
        options.roles,
      )}
      {filterSelect("level", "Level", level, setLevel, options.levels)}
      {filterSelect(
        "employment_type",
        "Employment",
        employmentType,
        setEmploymentType,
        options.employment,
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
        subtitle="Your job search, quantified."
      />

      <Tabs value={tab} onValueChange={changeTab} className="gap-5">
        <TabsList className="h-auto flex-wrap rounded-full bg-muted/70 p-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="market">Job market</TabsTrigger>
          <TabsTrigger value="fit">Resume fit</TabsTrigger>
          <TabsTrigger value="gaps">Gaps &amp; growth</TabsTrigger>
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
                  Skills ranked by how often they appear. Top 30% are mandatory;
                  the rest follow below.
                </p>
              </CardHeader>
              <CardContent>
                <TopSkillsChart filters={filters} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>
                  Skill coverage by role category
                </CardTitle>
              </CardHeader>
              <CardContent>
                <HeatmapChart filters={filters} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Role mix over time</CardTitle>
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
                  Weekly average ATS composite. Tailored resumes are solid
                  lines, base resumes dashed.
                </p>
              </CardHeader>
              <CardContent>
                <AtsOverTimeChart filters={filters} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Base → tailored lift</CardTitle>
                <p className="text-muted-foreground text-sm font-normal">
                  Average ATS composite before and after tailoring, by role
                  category.
                </p>
              </CardHeader>
              <CardContent>
                <TailoringLiftChart filters={filters} />
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Fit score distribution</CardTitle>
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
                Split by what would actually fix them: skills to learn vs.
                evidence to move. From your best-scoring resume per job.
                Wording-only mismatches sit in a footnote — they don&rsquo;t move
                your score.
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
