"use client";

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
  TOOLTIP_CONTENT_STYLE,
  TOOLTIP_ITEM_STYLE,
  TOOLTIP_LABEL_STYLE,
  weekLabel,
  weekTick,
} from "@/components/charts/chart-kit";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatWeekOf } from "@/lib/format-date";
import type { SearchSummary } from "@/lib/types";

/** Applied and replies per week of the period: two series on one count axis, applied first (`chart-1`), replies
 * second (`chart-2`). A reply counts in the week it came; one the migration backfilled has no week, and the
 * caption counts those. */
export function EachWeekChart({ summary, className }: { summary: SearchSummary; className?: string }) {
  const series = summary.series;
  const hasAny = series.some((week) => week.applied > 0 || week.replies > 0);
  const undated = summary.undated_replies;
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Each week</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!hasAny ? (
          <p className="text-muted-foreground text-body-medium">No applications or replies in this period.</p>
        ) : (
          <>
            <div aria-hidden="true">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={series} barGap={2} barCategoryGap="20%">
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="week_start"
                    tickFormatter={weekTick}
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={24}
                  />
                  <YAxis allowDecimals={false} fontSize={11} tickLine={false} axisLine={false} width={28} />
                  <Tooltip
                    labelFormatter={weekLabel}
                    contentStyle={TOOLTIP_CONTENT_STYLE}
                    labelStyle={TOOLTIP_LABEL_STYLE}
                    itemStyle={TOOLTIP_ITEM_STYLE}
                    cursor={{ fill: "var(--surface-container)" }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="applied" name="Applied" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} maxBarSize={24} />
                  <Bar dataKey="replies" name="Replies" fill={CHART_COLORS[1]} radius={[4, 4, 0, 0]} maxBarSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            {/* The chart's numbers for a screen reader: the bars are hidden, this table is not. */}
            <table className="sr-only">
              <caption>Applied and replies each week</caption>
              <thead>
                <tr>
                  <th scope="col">Week</th>
                  <th scope="col">Applied</th>
                  <th scope="col">Replies</th>
                </tr>
              </thead>
              <tbody>
                {series.map((week) => (
                  <tr key={week.week_start}>
                    <th scope="row">{formatWeekOf(week.week_start)}</th>
                    <td>{week.applied}</td>
                    <td>{week.replies}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {undated > 0 ? (
          <p className="text-muted-foreground text-body-small">
            {undated === 1
              ? "1 reply was recorded before Maestro kept dates, so no week shows it."
              : `${undated} replies were recorded before Maestro kept dates, so no week shows them.`}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
