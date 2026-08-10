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
import { CHART_COLORS as COLORS, buildQuery, TOOLTIP_CONTENT_STYLE, TOOLTIP_ITEM_STYLE, TOOLTIP_LABEL_STYLE } from "@/components/charts/chart-kit";
import { apiFetch } from "@/lib/api";
import type { TailoringLiftRow } from "@/lib/types";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

export function TailoringLiftChart({ filters }: { filters: TopSkillsFilters }) {
  const { data, isLoading } = useQuery({
    queryKey: ["explore", "tailoring-lift", filters],
    queryFn: () =>
      apiFetch<TailoringLiftRow[]>(
        `/api/explore/tailoring-lift?${buildQuery(filters)}`,
      ),
  });

  // The "all" row is the cross-role summary, not a role — pull it out of the
  // bars and surface it as a caption so it isn't mistaken for a category.
  const { chartData, overall } = useMemo(() => {
    const rows = data ?? [];
    const overall = rows.find((r) => r.role_category === "all") ?? null;
    const chartData = rows
      .filter((r) => r.role_category !== "all")
      .map((r) => ({
        role: r.role_category,
        Base: r.avg_base,
        Tailored: r.avg_tailored,
      }));
    return { chartData, overall };
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (!data || data.length === 0) {
    return <p className="text-muted-foreground text-sm">No data yet.</p>;
  }

  return (
    <div>
      {overall ? (
        <p className="text-muted-foreground mb-2 text-xs">
          Overall (all roles): {overall.avg_base.toFixed(1)} →{" "}
          {overall.avg_tailored.toFixed(1)}{" "}
          <span
            className={
              overall.avg_lift >= 0 ? "text-emerald-600" : "text-red-600"
            }
          >
            ({overall.avg_lift >= 0 ? "+" : ""}
            {overall.avg_lift.toFixed(1)})
          </span>{" "}
          across {overall.n} application{overall.n === 1 ? "" : "s"}.
        </p>
      ) : null}
      {chartData.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No per-role tailoring pairs yet.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="role" />
            <YAxis domain={[0, 100]} />
            <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
            <Legend />
            <Bar dataKey="Base" fill={COLORS[4]} />
            <Bar dataKey="Tailored" fill={COLORS[2]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
