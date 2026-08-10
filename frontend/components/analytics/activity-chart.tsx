"use client";

import { useState } from "react";
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

import {
  CHART_COLORS,
  ChartCard,
  TOOLTIP_CONTENT_STYLE,
  TOOLTIP_ITEM_STYLE,
  TOOLTIP_LABEL_STYLE,
} from "@/components/charts/chart-kit";
import type { SourceFilter } from "@/components/source-toggle";
import { apiFetch } from "@/lib/api";
import type { ActivityResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const GRANULARITIES = [
  { value: "day", label: "Day", weeks: 4 },
  { value: "week", label: "Week", weeks: 12 },
] as const;

export function ActivityChart({
  source = "all",
}: {
  source?: SourceFilter;
}) {
  const [granularity, setGranularity] = useState<"day" | "week">("day");
  const weeks = GRANULARITIES.find((g) => g.value === granularity)!.weeks;

  const { data, isLoading, error } = useQuery({
    queryKey: ["explore", "activity", granularity, weeks, source],
    queryFn: () => {
      const params = new URLSearchParams({
        granularity,
        weeks: String(weeks),
      });
      if (source === "user" || source === "agent") params.set("source", source);
      return apiFetch<ActivityResponse>(`/api/explore/activity?${params}`);
    },
  });

  const series = data?.series ?? [];
  const hasAny = series.some((row) => row.drafted > 0 || row.submitted > 0);

  return (
    <ChartCard
      title="Application activity"
      description="Drafts started and applications submitted over time."
      isLoading={isLoading}
      error={error as Error | null}
    >
      {/* The toggle stays outside the empty gate: an empty Day window must
          still let the user reach the longer Week window. */}
      <div
        role="group"
        aria-label="Activity granularity"
        className="mb-3 inline-flex rounded-full bg-muted/70 p-1"
      >
        {GRANULARITIES.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={granularity === option.value}
            onClick={() => setGranularity(option.value)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors duration-150 ease-out",
              granularity === option.value
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      {!hasAny ? (
        <p className="text-muted-foreground text-sm">
          No application activity in this window yet.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={series} barGap={2}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} vertical={false} />
            <XAxis
              dataKey="bucket_start"
              tickFormatter={(value: string) => value.slice(5)}
              fontSize={11}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
            />
            <YAxis
              allowDecimals={false}
              fontSize={11}
              tickLine={false}
              axisLine={false}
              width={28}
            />
            <Tooltip
              contentStyle={TOOLTIP_CONTENT_STYLE}
              labelStyle={TOOLTIP_LABEL_STYLE}
              itemStyle={TOOLTIP_ITEM_STYLE}
              cursor={{ fill: "var(--muted)", opacity: 0.4 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {/* Emphasis: submitted is the story (accent); drafted is context. */}
            <Bar
              dataKey="submitted"
              name="Submitted"
              fill={CHART_COLORS[0]}
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="drafted"
              name="Drafted"
              fill="var(--muted-foreground)"
              fillOpacity={0.35}
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
