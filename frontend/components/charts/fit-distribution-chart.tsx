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
import { splitTopSeries } from "@/lib/analytics-series";
import { apiFetch } from "@/lib/api";
import { baseResumeLabel, type FitDistributionRow } from "@/lib/types";

const BUCKETS = ["0-20", "20-40", "40-60", "60-80", "80-100"] as const;

export function FitDistributionChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "fit-distribution"],
    queryFn: () =>
      apiFetch<FitDistributionRow[]>("/api/explore/fit-distribution"),
  });

  // One hue per resume and six hues, so the resumes with the most scores are
  // drawn and the rest are named in the caption, never recoloured. dataKey is
  // the slug (two resumes can share a name); `name` is what the legend says.
  const { chartData, drawn, hidden } = useMemo(() => {
    if (!data) {
      return { chartData: [], drawn: [] as FitDistributionRow[], hidden: [] as string[] };
    }
    const { shown, hidden } = splitTopSeries(
      data,
      (row) => row.base_resume,
      (row) => row.n,
      COLORS.length,
    );
    const drawn = shown.flatMap((slug) => data.filter((row) => row.base_resume === slug));
    const chartData = BUCKETS.map((bucket) => ({
      bucket,
      ...Object.fromEntries(drawn.map((row) => [row.base_resume, row.buckets[bucket] ?? 0])),
    }));
    return { chartData, drawn, hidden };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  const caption = [
    drawn.some((d) => d.low_sample)
      ? "Some resumes have fewer than 5 scores · those series are directional only."
      : "",
    hidden.length
      ? `Showing the ${COLORS.length} resumes with the most scores. ${hidden.length} more ${hidden.length === 1 ? "is" : "are"} not shown.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div>
      {caption ? (
        <p className="text-muted-foreground mb-2 text-xs">{caption}</p>
      ) : null}
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="bucket" />
          <YAxis allowDecimals={false} />
          <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
          <Legend />
          {drawn.map((row, i) => (
            <Bar
              key={row.base_resume}
              dataKey={row.base_resume}
              name={row.display_name ?? baseResumeLabel(row.base_resume)}
              fill={COLORS[i]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
