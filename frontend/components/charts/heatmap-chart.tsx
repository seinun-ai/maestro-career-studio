"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { buildQuery, chartGate } from "@/components/charts/chart-kit";
import { useRoleLabel } from "@/components/role-category-picker";
import { apiFetch } from "@/lib/api";
import { MIN_RATE_N, rateWords } from "@/lib/rates";
import type { HeatmapRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";
import { skillName } from "@/lib/skill-name";
import { cn } from "@/lib/utils";

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
  const query = useQuery({
    queryKey: ["explore", "heatmap", filters, limit],
    queryFn: () =>
      apiFetch<HeatmapRow[]>(
        `/api/explore/heatmap?${buildQuery(filters ?? {}, { limit, top_tier_only: "true" })}`,
      ),
  });
  const { data } = query;

  const label = useRoleLabel();

  const { skills, roles, matrix, jobsIn } = useMemo(() => {
    const skills = new Set<string>();
    const roles = new Set<string>();
    const matrix = new Map<string, HeatmapRow>();
    // Each role's job count, the denominator of every share in its column.
    const jobsIn = new Map<string, number>();
    for (const row of data ?? []) {
      skills.add(row.skill_name);
      roles.add(row.role_category);
      matrix.set(`${row.skill_name}|${row.role_category}`, row);
      jobsIn.set(row.role_category, row.of);
    }
    return {
      skills: [...skills].sort(),
      roles: [...roles].sort(),
      matrix,
      jobsIn,
    };
  }, [data]);

  const gate = chartGate(query, { errorTitle: "Couldn't load skills by role.", empty: !data || data.length === 0 });
  if (gate) return gate;

  return (
    <div className="overflow-x-auto">
      <p className="text-muted-foreground mb-3 text-body-small">
        Share of jobs in each role that ask for each skill. Shows the top 30% of skills, the ones jobs ask for most.
        A role with fewer than {MIN_RATE_N} jobs shows its counts, such as 2 of 3.
      </p>
      <table className="border-separate border-spacing-0.5 text-body-small">
        <thead>
          <tr>
            <th className="sticky left-0 bg-background p-1"></th>
            {roles.map((role) => (
              <th
                key={role}
                className="max-w-28 p-1 text-left align-bottom text-label-medium"
              >
                {label(role)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {skills.map((skill) => (
            <tr key={skill}>
              <th className="sticky left-0 bg-background pr-2 text-left text-label-medium whitespace-nowrap">
                {skillName(skill)}
              </th>
              {roles.map((role) => {
                const row = matrix.get(`${skill}|${role}`);
                const of = row?.of ?? jobsIn.get(role) ?? 0;
                const count = row?.count ?? 0;
                // D7: a share from MIN_RATE_N jobs in the role; below that the counts, coloured as no share.
                const share = { count, of, rate: of ? count / of : null, low: null, high: null };
                const words = rateWords(share).value;
                const counts = of < MIN_RATE_N;
                return (
                  <td
                    key={role}
                    title={`${skillName(skill)} · ${label(role)}: ${words}`}
                    className={cn(
                      "h-8 min-w-12 rounded-corner-xs text-center align-middle text-label-small",
                      counts && "bg-surface-container-high",
                    )}
                    style={counts ? undefined : { backgroundColor: cellColor((count / of) * 100) }}
                  >
                    {count > 0 ? words : ""}
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
