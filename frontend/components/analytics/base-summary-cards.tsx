"use client";

import Link from "next/link";
import { InlineStat } from "@/components/analytics/stat-tile";
import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { formatTimeAgo } from "@/lib/format-date";
import type { BaseSummaryRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
  B: "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
  C: "bg-amber-500/15 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
  D: "bg-destructive/10 text-destructive",
  F: "bg-destructive/10 text-destructive",
};

export function BaseSummaryCards() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["explore", "base-summaries"],
    queryFn: () => apiFetch<BaseSummaryRow[]>("/api/explore/base-summaries"),
  });

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-40 w-full" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <p role="alert" className="text-destructive text-sm">
        {(error as Error).message}
      </p>
    );
  }
  if ((data ?? []).length === 0) {
    return <p className="text-muted-foreground text-sm">No base resumes yet.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {(data ?? []).map((row) => (
        <Card key={row.slug} className="rounded-2xl">
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle>
              <Link
                href={`/base-resumes/${row.slug}`}
                className="hover:underline"
              >
                {row.display_name ?? row.slug}
              </Link>
            </CardTitle>
            {row.health_grade ? (
              <span
                className={cn(
                  "inline-flex h-6 shrink-0 items-center rounded-full px-2 text-xs font-medium",
                  GRADE_STYLES[row.health_grade] ?? "bg-muted text-muted-foreground",
                )}
                title={
                  row.health_score != null
                    ? `Health ${row.health_score}/100`
                    : undefined
                }
              >
                Health {row.health_grade}
              </span>
            ) : (
              <span className="text-muted-foreground inline-flex h-6 shrink-0 items-center rounded-full bg-muted px-2 text-xs">
                No health check
              </span>
            )}
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2.5">
              <InlineStat
                label="Avg base ATS"
                value={
                  row.avg_base_ats != null
                    ? `${row.avg_base_ats} · ${row.n_scored} ${row.n_scored === 1 ? "job" : "jobs"}`
                    : "—"
                }
              />
              <InlineStat
                label="Avg lift"
                value={
                  row.avg_lift != null
                    ? `${row.avg_lift > 0 ? "+" : ""}${row.avg_lift} · ${row.n_tailored} tailored`
                    : "—"
                }
              />
              <InlineStat
                label="Applications"
                value={`${row.applications_submitted} sent · ${row.applications_total} total`}
              />
              <InlineStat label="In flight" value={String(row.in_flight)} />
            </div>
            {row.last_activity ? (
              <p className="text-muted-foreground mt-3 text-xs">
                Active {formatTimeAgo(row.last_activity)}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
