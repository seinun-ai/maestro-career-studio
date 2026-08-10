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
import { CHART_COLORS as COLORS, TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE } from "@/components/charts/chart-kit";
import { apiFetch } from "@/lib/api";
import type { RoleMixRow } from "@/lib/types";
import { roleCategoryLabel } from "@/lib/format";

export function RoleMixChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "role-mix-over-time"],
    queryFn: () =>
      apiFetch<RoleMixRow[]>("/api/explore/role-mix-over-time?window=week"),
  });

  const { chartData, categories } = useMemo(() => {
    if (!data) return { chartData: [], categories: [] as string[] };
    const weeks = new Map<string, Record<string, number | string>>();
    const categorySet = new Set<string>();
    for (const row of data) {
      categorySet.add(row.role_category);
      const bucket = weeks.get(row.week_start) ?? { week: row.week_start };
      bucket[row.role_category] = ((bucket[row.role_category] as number) ?? 0) + row.count;
      weeks.set(row.week_start, bucket);
    }
    const chartData = [...weeks.values()].sort((a, b) =>
      String(a.week).localeCompare(String(b.week)),
    );
    return { chartData, categories: [...categorySet].sort() };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (chartData.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="week" />
        <YAxis allowDecimals={false} />
        <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
        <Legend />
        {categories.map((cat, i) => (
          <Area
            key={cat}
            type="monotone"
            dataKey={cat}
            name={roleCategoryLabel(cat)}
            stackId="1"
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.6}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
