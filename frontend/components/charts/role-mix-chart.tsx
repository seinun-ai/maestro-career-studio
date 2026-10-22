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

import { CHART_COLORS as COLORS, buildQuery, chartGate, TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE, weekLabel, weekRows, weekTick } from "@/components/charts/chart-kit";
import { useRoleLabel } from "@/components/role-category-picker";
import { splitTopSeries } from "@/lib/analytics-series";
import { apiFetch } from "@/lib/api";
import type { RoleMixRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

const MORE_ROLES = "__more__";

export function RoleMixChart({ filters }: { filters: TopSkillsFilters }) {
  const query = useQuery({
    queryKey: ["explore", "role-mix-over-time", filters],
    queryFn: () =>
      apiFetch<RoleMixRow[]>(
        `/api/explore/role-mix-over-time?${buildQuery(filters, { window: "week" })}`,
      ),
  });
  const { data } = query;

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
    const chartData = weekRows(
      data,
      (row) => (shownSet.has(row.role_category) ? row.role_category : MORE_ROLES),
      (row, sum) => (sum ?? 0) + row.count,
    );
    const categories = hidden.length ? [...shown, MORE_ROLES] : shown;
    // Weeks each series has a value in: an area needs two, so a lone week draws as a dot.
    const points = new Map(
      categories.map((cat) => [cat, chartData.filter((week) => week[cat] !== undefined).length]),
    );
    return { chartData, categories, points };
  }, [data]);

  const gate = chartGate(query, { errorTitle: "Couldn't load roles over time.", empty: chartData.length === 0 });
  if (gate) return gate;

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
