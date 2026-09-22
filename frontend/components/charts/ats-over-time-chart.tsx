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
import { useRoleLabel } from "@/components/role-category-picker";
import { MAX_ROLE_SERIES, splitTopRoles } from "@/lib/analytics-series";
import { apiFetch } from "@/lib/api";
import type { AtsOverTimeRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

const PHASE_LABEL = { base: "Base", tailored: "Tailored" } as const;

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

  // One role selected → collapse series to just base/tailored; otherwise the
  // top roles by score count, tail excluded so colours never cycle. Base is
  // always dashed, tailored solid. dataKey stays the slug; `name` is the label.
  const singleRole = Boolean(filters.role_category);
  const label = useRoleLabel();

  const { chartData, series, hidden, anyLow } = useMemo(() => {
    if (!data) {
      return {
        chartData: [],
        series: [] as Series[],
        hidden: [] as string[],
        anyLow: false,
      };
    }

    const split = singleRole
      ? { shown: [...new Set(data.map((row) => row.role_category))], hidden: [] as string[] }
      : splitTopRoles(data, (row) => row.role_category, (row) => row.n);
    const drawn = singleRole
      ? data
      : data.filter((row) => split.shown.includes(row.role_category));
    const roleColor = (role: string) => COLORS[split.shown.indexOf(role)];

    const weeks = new Map<string, Record<string, number | string>>();
    const seriesMeta = new Map<string, SeriesMeta>();
    for (const row of drawn) {
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

    return {
      chartData,
      series,
      hidden: split.hidden,
      anyLow: drawn.some((row) => row.low_sample),
    };
  }, [data, singleRole]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (chartData.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <div>
      <p className="text-muted-foreground mb-2 text-xs">
        Solid = tailored · dashed = base. Weekly average ATS composite (0–100).
        {anyLow
          ? " Weeks with fewer than 5 scores are directional only."
          : ""}
        {hidden.length
          ? ` Showing the ${MAX_ROLE_SERIES} roles with the most scores. Pick a role category above to see the other ${hidden.length}.`
          : ""}
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
              name={
                singleRole
                  ? PHASE_LABEL[meta.phase]
                  : `${label(meta.role)} · ${PHASE_LABEL[meta.phase]}`
              }
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
