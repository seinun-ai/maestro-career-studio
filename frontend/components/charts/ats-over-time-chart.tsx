"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Skeleton } from "@/components/ui/skeleton";
import { CHART_COLORS as COLORS, buildQuery, TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE } from "@/components/charts/chart-kit";
import { apiFetch } from "@/lib/api";
import type { AtsOverTimeRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

interface SeriesMeta {
  role: string;
  phase: "base" | "tailored";
}

interface Series {
  key: string;
  meta: SeriesMeta;
  stroke: string;
}

export function AtsOverTimeChart({ filters }: { filters: TopSkillsFilters }) {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "ats-over-time", filters],
    queryFn: () =>
      apiFetch<AtsOverTimeRow[]>(
        `/api/explore/ats-over-time?${buildQuery(filters)}`,
      ),
  });

  // One role selected → collapse series to just base/tailored; otherwise one
  // series per role_category + phase. Base is always dashed, tailored solid.
  const singleRole = Boolean(filters.role_category);

  const { chartData, series } = useMemo(() => {
    if (!data) return { chartData: [], series: [] as Series[] };

    const roles = [...new Set(data.map((r) => r.role_category))].sort();
    const roleColor = (role: string) =>
      COLORS[Math.max(0, roles.indexOf(role)) % COLORS.length];

    const weeks = new Map<string, Record<string, number | string>>();
    const seriesMeta = new Map<string, SeriesMeta>();
    for (const row of data) {
      const key = singleRole
        ? row.phase
        : `${row.role_category} · ${row.phase}`;
      seriesMeta.set(key, { role: row.role_category, phase: row.phase });
      const bucket = weeks.get(row.week_start) ?? { week: row.week_start };
      bucket[key] = row.avg_composite;
      weeks.set(row.week_start, bucket);
    }

    const chartData = [...weeks.values()].sort((a, b) =>
      String(a.week).localeCompare(String(b.week)),
    );
    const series = [...seriesMeta.keys()].sort().map((key) => {
      const meta = seriesMeta.get(key)!;
      const stroke = singleRole
        ? meta.phase === "tailored"
          ? COLORS[0]
          : COLORS[4]
        : roleColor(meta.role);
      return { key, meta, stroke };
    });

    return { chartData, series };
  }, [data, singleRole]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (chartData.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <div>
      <p className="text-muted-foreground mb-2 text-xs">
        Solid = tailored · dashed = base. Weekly average ATS composite (0–100).
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="week" />
          <YAxis domain={[0, 100]} />
          <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
          <Legend />
          {series.map(({ key, meta, stroke }) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={stroke}
              strokeDasharray={meta.phase === "base" ? "5 5" : undefined}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
