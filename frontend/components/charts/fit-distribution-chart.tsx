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
import { TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE } from "@/components/charts/chart-kit";
import { ResumeTag } from "@/components/visual";
import { useBaseResumeColor } from "@/hooks/use-base-resume-label";
import { useResumeSwatchTones } from "@/hooks/use-resume-swatch-tones";
import { splitTopSeries } from "@/lib/analytics-series";
import { apiFetch } from "@/lib/api";
import { resumeSwatchColor } from "@/lib/resume-color";
import { baseResumeLabel, type FitDistributionRow } from "@/lib/types";

const BUCKETS = ["0-20", "20-40", "40-60", "60-80", "80-100"] as const;
/** Grouped bars stop reading past this many resumes. */
const MAX_FIT_SERIES = 6;

export function FitDistributionChart() {
  const colorOf = useBaseResumeColor();
  const tones = useResumeSwatchTones();
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "fit-distribution"],
    queryFn: () =>
      apiFetch<FitDistributionRow[]>("/api/explore/fit-distribution"),
  });

  // A chart split by base resume colours each series by its resume (identity, not the chart-1..6 palette),
  // so a resume keeps its colour across the app. Six series at most: the resumes with the most scores are
  // drawn and the rest are named in the caption. dataKey is the slug (two resumes can share a name); `name`
  // is what the legend says.
  const { chartData, drawn, hidden } = useMemo(() => {
    if (!data) {
      return { chartData: [], drawn: [] as FitDistributionRow[], hidden: [] as string[] };
    }
    const { shown, hidden } = splitTopSeries(
      data,
      (row) => row.base_resume,
      (row) => row.n,
      MAX_FIT_SERIES,
    );
    const drawn = shown.flatMap((slug) => data.filter((row) => row.base_resume === slug));
    // The keys are the server's ("0-20"); a range on screen takes an en dash.
    const chartData = BUCKETS.map((bucket) => ({
      bucket: bucket.replace("-", "–"),
      ...Object.fromEntries(drawn.map((row) => [row.base_resume, row.buckets[bucket] ?? 0])),
    }));
    return { chartData, drawn, hidden };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground text-body-medium">No data yet.</p>;
  }

  const caption = [
    drawn.some((d) => d.low_sample)
      ? "Some resumes have fewer than 5 scores, so treat those lines as rough."
      : "",
    hidden.length
      ? `Showing the ${MAX_FIT_SERIES} resumes with the most scores. ${hidden.length} more ${hidden.length === 1 ? "is" : "are"} not shown.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div>
      {caption ? (
        <p className="text-muted-foreground mb-2 text-body-small">{caption}</p>
      ) : null}
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="bucket" />
          <YAxis allowDecimals={false} />
          <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
          <Legend
            content={({ payload }) => (
              <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-body-small">
                {payload?.map((entry) => (
                  <li key={String(entry.dataKey)}>
                    <ResumeTag hue={colorOf(String(entry.dataKey))}>{entry.value}</ResumeTag>
                  </li>
                ))}
              </ul>
            )}
          />
          {drawn.map((row) => (
            <Bar
              key={row.base_resume}
              dataKey={row.base_resume}
              name={row.display_name ?? baseResumeLabel(row.base_resume)}
              fill={resumeSwatchColor(colorOf(row.base_resume), tones)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
