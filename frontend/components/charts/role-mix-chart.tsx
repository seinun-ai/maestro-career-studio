"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Skeleton } from "@/components/ui/skeleton";
import { CHART_COLORS as COLORS, buildQuery, TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE, weekLabel, weekTick } from "@/components/charts/chart-kit";
import { useRoleLabel } from "@/components/role-category-picker";
import { splitTopSeries } from "@/lib/analytics-series";
import { apiFetch } from "@/lib/api";
import type { RoleMixRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

const MORE_ROLES = "__more__";

export function RoleMixChart({ filters }: { filters: TopSkillsFilters }) {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "role-mix-over-time", filters],
    queryFn: () =>
      apiFetch<RoleMixRow[]>(
        `/api/explore/role-mix-over-time?${buildQuery(filters, { window: "week" })}`,
      ),
  });

  const label = useRoleLabel();

  // Counts add, so the tail is one honest "More roles" bucket (not "Other",
  // which is a real category). Five named roles plus that bucket is 6 hues.
  const { chartData, categories, points } = useMemo(() => {
    if (!data) return { chartData: [], categories: [] as string[], points: new Map<string, number>() };
    const { shown, hidden } = splitTopSeries(
      data,
      (row) => row.role_category,
      (row) => row.count,
      5,
    );
    const shownSet = new Set(shown);
    const weeks = new Map<string, Record<string, number | string>>();
    for (const row of data) {
      const key = shownSet.has(row.role_category) ? row.role_category : MORE_ROLES;
      const bucket = weeks.get(row.week_start) ?? { week: row.week_start };
      bucket[key] = ((bucket[key] as number) ?? 0) + row.count;
      weeks.set(row.week_start, bucket);
    }
    const chartData = [...weeks.values()].sort((a, b) =>
      String(a.week).localeCompare(String(b.week)),
    );
    const categories = hidden.length ? [...shown, MORE_ROLES] : shown;
    // Weeks each series has a value in: an area needs two, so a lone week draws as a dot.
    const points = new Map(
      categories.map((cat) => [cat, chartData.filter((week) => week[cat] !== undefined).length]),
    );
    return { chartData, categories, points };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (chartData.length === 0) {
    return <p className="text-muted-foreground text-body-medium">No data yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="week" tickFormatter={weekTick} />
        <YAxis allowDecimals={false} />
        <Tooltip labelFormatter={weekLabel} contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
        <Legend />
        {categories.map((cat, i) => (
          <Area
            key={cat}
            type="monotone"
            dataKey={cat}
            name={cat === MORE_ROLES ? "More roles" : label(cat)}
            stackId="1"
            stroke={COLORS[i]}
            fill={COLORS[i]}
            fillOpacity={0.6}
            dot={points.get(cat) === 1}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
