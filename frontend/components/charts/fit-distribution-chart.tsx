"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
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
import { baseResumeLabel, type FitDistributionRow } from "@/lib/types";

const BUCKETS = ["0-20", "20-40", "40-60", "60-80", "80-100"] as const;

function resumeLabel(slug: string): string {
  return baseResumeLabel(slug);
}

export function FitDistributionChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "fit-distribution"],
    queryFn: () =>
      apiFetch<FitDistributionRow[]>("/api/explore/fit-distribution"),
  });

  const chartData = useMemo(() => {
    if (!data) return [];
    return BUCKETS.map((bucket) => {
      const row: Record<string, string | number> = { bucket };
      for (const item of data) {
        row[resumeLabel(item.base_resume)] = item.buckets[bucket] ?? 0;
      }
      return row;
    });
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  const resumeKeys = data.map((d) => resumeLabel(d.base_resume));

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="bucket" />
        <YAxis allowDecimals={false} />
        <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
        <Legend />
        {resumeKeys.map((key, i) => (
          <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
