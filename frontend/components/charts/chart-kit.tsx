"use client";

import type { CSSProperties, ReactElement, ReactNode } from "react";

import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";
import { LoadErrorState } from "@/components/load-error-state";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { formatShortDate, formatWeekOf } from "@/lib/format-date";
import { isLoadFailure, type LoadQuery } from "@/lib/query-state";

/** A weekly chart's axis ("Sep 21") and tooltip ("Week of Sep 21"): an ISO day read as machine output. */
export const weekTick = (value: unknown) => formatShortDate(String(value));
export const weekLabel = (value: unknown) => formatWeekOf(String(value));

/**
 * Categorical palette, fixed assignment order (never cycle or generate hues).
 * Values live in globals.css (--chart-1..6, OKLCH, light + dark); the
 * fallbacks are the light steps.
 */
export const CHART_COLORS = [
  "var(--chart-1, oklch(0.55 0.14 259))",
  "var(--chart-2, oklch(0.62 0.13 50))",
  "var(--chart-3, oklch(0.55 0.1 175))",
  "var(--chart-4, oklch(0.55 0.14 310))",
  "var(--chart-5, oklch(0.6 0.11 95))",
  "var(--chart-6, oklch(0.5 0.03 259))",
];

/** Theme-aware styles for recharts' default <Tooltip />. */
export const TOOLTIP_CONTENT_STYLE: CSSProperties = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-corner-xs)",
  fontSize: 12,
  color: "var(--popover-foreground)",
  boxShadow: "var(--shadow-level2)",
};
export const TOOLTIP_LABEL_STYLE: CSSProperties = {
  color: "var(--popover-foreground)",
  fontWeight: 500,
};
export const TOOLTIP_ITEM_STYLE: CSSProperties = {
  color: "var(--popover-foreground)",
};

export function buildQuery(
  filters: TopSkillsFilters,
  extra?: Record<string, string | number>,
): string {
  const params = new URLSearchParams();
  if (filters.role_category) params.set("role_category", filters.role_category);
  if (filters.level) params.set("level", filters.level);
  if (filters.employment_type)
    params.set("employment_type", filters.employment_type);
  if (filters.country) params.set("country", filters.country);
  if (filters.salary_currency)
    params.set("salary_currency", filters.salary_currency);
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      params.set(k, String(v));
    }
  }
  return params.toString();
}

/**
 * What a chart shows before it can draw, or null once it can. A failed fetch is its own state, never "No data
 * yet." (conventions), and it comes before the loading gate: a retry of a data-less query would otherwise
 * paint the skeleton and drop focus. Then the skeleton while it loads, then No data yet when `empty`.
 */
export function chartGate(
  query: LoadQuery & { error: Error | null; isLoading: boolean; isFetching: boolean; refetch: () => unknown },
  { errorTitle, empty, skeleton = "h-80 w-full" }: { errorTitle: string; empty: boolean; skeleton?: string },
): ReactElement | null {
  if (isLoadFailure(query)) {
    return (
      <LoadErrorState
        className="py-8"
        title={errorTitle}
        detail={loadErrorDetail(query.error)}
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isLoading) return <Skeleton className={skeleton} />;
  if (empty) return <p className="text-muted-foreground text-body-medium">No data yet.</p>;
  return null;
}

/** Uniform analytics panel: title + optional one-clause description + states. */
export function ChartCard({
  title,
  description,
  className,
  isLoading,
  error,
  empty,
  emptyText = "No data yet.",
  action,
  children,
}: {
  title: string;
  description?: string;
  className?: string;
  isLoading?: boolean;
  error?: Error | null;
  empty?: boolean;
  emptyText?: string;
  /** Card-level control (not a legend or a filter — those belong in the body).
   *  Rendered in the header via the card primitive's own CardAction slot, which
   *  is what re-columns CardHeader; a hand-rolled absolutely-positioned box
   *  here would be the 14th containment box in this codebase. Sits OUTSIDE the
   *  loading/error/empty switch below on purpose: "clear this data" has to stay
   *  reachable while the body is showing an error. */
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? (
          <p className="text-muted-foreground text-body-medium">{description}</p>
        ) : null}
        {action ? <CardAction>{action}</CardAction> : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : error ? (
          <p role="alert" className="text-destructive text-body-medium">
            {couldnt("load this chart", error)}
          </p>
        ) : empty ? (
          <p className="text-muted-foreground text-body-medium">{emptyText}</p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
