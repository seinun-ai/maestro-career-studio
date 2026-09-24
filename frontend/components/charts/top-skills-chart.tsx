"use client";

import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { buildQuery } from "@/components/charts/chart-kit";
import { LoadErrorState } from "@/components/load-error-state";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import { skillName } from "@/lib/skill-name";
import type { TopSkillRow, TopSkillsResponse } from "@/lib/types";
import { LowSampleBadge } from "@/components/explore/low-sample-hint";

export interface TopSkillsFilters {
  role_category?: string | null;
  level?: string | null;
  employment_type?: string | null;
  country?: string | null;
  salary_currency?: string | null;
}

function jobCountLabel(n: number): string {
  return `${n} ${n === 1 ? "job" : "jobs"}`;
}

function SkillPill({
  skill,
  pillClass,
}: {
  skill: TopSkillRow;
  pillClass: string;
}) {
  const tooltip = skill.low_sample
    ? `${jobCountLabel(skill.n)} · Rank ${skill.rank} · small sample`
    : `${jobCountLabel(skill.n)} · Rank ${skill.rank}`;

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            className={cn(
              "inline-flex cursor-default items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
              pillClass,
            )}
            title={tooltip}
          >
            <span className="text-on-secondary-container/80 text-[10px] font-semibold tabular-nums">
              #{skill.rank}
            </span>
            {skillName(skill.skill_name)}
            <LowSampleBadge n={skill.n} lowSample={skill.low_sample} unit="jobs" />
          </span>
        }
      />
      <TooltipContent side="top">{tooltip}</TooltipContent>
    </Tooltip>
  );
}

function SkillTileSection({
  label,
  subtitle,
  count,
  skills,
  pillClass,
  bandClass,
}: {
  label: string;
  subtitle?: string;
  count: number;
  skills: TopSkillRow[];
  pillClass: string;
  bandClass?: string;
}) {
  return (
    <section className={cn(bandClass)}>
      <div className="flex gap-4 sm:gap-6">
        <div className="w-20 shrink-0 pt-1 text-right sm:w-24">
          <p className="text-sm leading-tight font-semibold">{label}</p>
          <p className="text-muted-foreground mt-0.5 text-xs tabular-nums">({count})</p>
          {subtitle ? (
            <p className="text-muted-foreground mt-0.5 text-xs">{subtitle}</p>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap gap-2">
          {skills.length === 0 ? (
            <p className="text-muted-foreground py-1 text-sm">No skills here.</p>
          ) : (
            skills.map((skill) => (
              <SkillPill
                key={`${skill.skill_name}-${skill.skill_category}`}
                skill={skill}
                pillClass={pillClass}
              />
            ))
          )}
        </div>
      </div>
    </section>
  );
}

export function TopSkillsChart({
  filters,
  limit = 50,
}: {
  filters: TopSkillsFilters;
  limit?: number;
}) {
  const query = useQuery({
    queryKey: ["explore", "top-skills", filters, limit],
    queryFn: () =>
      apiFetch<TopSkillsResponse>(`/api/explore/top-skills?${buildQuery(filters, { limit })}`),
  });
  const { data, isLoading } = query;

  // A failed fetch is its own state, never "No data yet." (conventions).
  if (isLoadFailure(query)) {
    return (
      <LoadErrorState
        className="py-8"
        title="Couldn't load the top skills."
        detail={loadErrorDetail(query.error)}
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data || (data.top.length === 0 && data.rest.length === 0)) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <div className="space-y-0">
      <SkillTileSection
        label="Top 30%"
        subtitle="Most asked for"
        count={data.meta.top_count}
        skills={data.top}
        pillClass="border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"
        bandClass="bg-muted/30 rounded-lg p-3"
      />

      <div className="border-border my-5 border-t" />

      <SkillTileSection
        label="Others"
        count={data.meta.total_skills - data.meta.top_count}
        skills={data.rest}
        pillClass="border-border bg-background text-foreground hover:bg-muted/60 text-xs"
      />
    </div>
  );
}
