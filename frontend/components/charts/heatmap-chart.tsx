"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import { buildQuery } from "@/components/charts/chart-kit";
import { apiFetch } from "@/lib/api";
import type { HeatmapRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

function cellColor(pct: number): string {
  // Sequential single-hue ramp from the theme's primary blue (theme-aware,
  // unlike the old hard-coded violet rgba).
  const intensity = Math.min(1, pct / 100);
  const alpha = Math.round((0.1 + intensity * 0.8) * 100);
  return `color-mix(in oklab, var(--primary) ${alpha}%, transparent)`;
}

export function HeatmapChart({
  filters,
  limit = 15,
}: {
  filters?: TopSkillsFilters;
  limit?: number;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "heatmap", filters, limit],
    queryFn: () =>
      apiFetch<HeatmapRow[]>(
        `/api/explore/heatmap?${buildQuery(filters ?? {}, { limit, top_tier_only: "true" })}`,
      ),
  });

  const { skills, roles, matrix } = useMemo(() => {
    const skills = new Set<string>();
    const roles = new Set<string>();
    const matrix = new Map<string, number>();
    for (const row of data ?? []) {
      skills.add(row.skill_name);
      roles.add(row.role_category);
      matrix.set(`${row.skill_name}|${row.role_category}`, row.pct_jobs);
    }
    return {
      skills: [...skills].sort(),
      roles: [...roles].sort(),
      matrix,
    };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <p className="text-muted-foreground mb-3 text-xs">
        Top-30% skills by rank; cell = % of jobs in that role mentioning the skill.
      </p>
      <table className="border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 bg-background p-1"></th>
            {roles.map((role) => (
              <th
                key={role}
                className="max-w-24 p-1 text-left font-medium whitespace-nowrap"
              >
                {role}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {skills.map((skill) => (
            <tr key={skill}>
              <th className="sticky left-0 bg-background pr-2 text-left font-medium whitespace-nowrap">
                {skill}
              </th>
              {roles.map((role) => {
                const pct = matrix.get(`${skill}|${role}`) ?? 0;
                return (
                  <td
                    key={role}
                    title={`${skill} · ${role}: ${pct}%`}
                    className="h-8 min-w-12 rounded text-center align-middle text-[10px]"
                    style={{ backgroundColor: cellColor(pct) }}
                  >
                    {pct > 0 ? `${pct.toFixed(0)}%` : ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
