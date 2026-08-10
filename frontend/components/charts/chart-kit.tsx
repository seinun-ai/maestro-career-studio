"use client";

import type { CSSProperties, ReactNode } from "react";

import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { TopSkillsFilters } from "@/components/charts/top-skills-chart";

/**
 * Categorical palette, fixed assignment order (never cycle or generate hues).
 * Values live in globals.css (--chart-1..6, validated light + dark).
 */
export const CHART_COLORS = [
  "var(--chart-1, #4285f4)",
  "var(--chart-2, #ea4335)",
  "var(--chart-3, #e8710a)",
  "var(--chart-4, #188038)",
  "var(--chart-5, #9334e6)",
  "var(--chart-6, #0097a7)",
];

/** Theme-aware styles for recharts' default <Tooltip />. */
export const TOOLTIP_CONTENT_STYLE: CSSProperties = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--popover-foreground)",
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
          <p className="text-muted-foreground text-sm font-normal">{description}</p>
        ) : null}
        {action ? <CardAction>{action}</CardAction> : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : error ? (
          <p role="alert" className="text-destructive text-sm">
            {error.message}
          </p>
        ) : empty ? (
          <p className="text-muted-foreground text-sm">{emptyText}</p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
