"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { HeartPulse } from "lucide-react";

import { apiFetch } from "@/lib/api";

const COUNTS = [
  { key: "gate", label: "gate", className: "bg-red-500/15 text-red-600 dark:text-red-400" },
  { key: "critical", label: "critical", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  { key: "ask", label: "ask", className: "bg-violet-500/15 text-violet-600 dark:text-violet-400" },
  { key: "note", label: "note", className: "bg-slate-500/15 text-slate-600 dark:text-slate-400" },
] as const;

type LintReport = {
  score: number;
  grade: string;
  counts: Record<string, number>;
  created_at: string;
};

/**
 * The editor header's single health entry point: a link to the full-page
 * report. When a report exists it shows the grade + count chips; otherwise a
 * compact "Check health" link keeps the report (and its Analyze CTA)
 * discoverable.
 */
export function HealthBadges({
  kind,
  resumeKey,
  reportHref,
}: {
  kind: "base" | "application";
  resumeKey: string;
  /** Href of the full-page health report. */
  reportHref: string;
}) {
  const { data } = useQuery({
    queryKey: ["resume-lint", kind, resumeKey],
    queryFn: () =>
      apiFetch<LintReport>(`/api/resume-lint/${kind}/${resumeKey}`),
    retry: false,
    staleTime: 60_000,
  });

  // Both states share the same bordered pill so health reads as one control in
  // the header row rather than loose chips floating between the buttons — it
  // was easy to miss entirely at a glance.
  const shell =
    "hover:bg-muted/60 hover:border-border flex items-center gap-1.5 rounded-md " +
    "border border-transparent bg-muted/40 px-2 py-1 transition-colors";

  if (!data) {
    return (
      <Link
        href={reportHref}
        className={`${shell} text-muted-foreground hover:text-foreground text-sm`}
        title="Check this resume's health"
      >
        <HeartPulse className="size-4" /> Check health
      </Link>
    );
  }

  return (
    <Link
      href={reportHref}
      className={shell}
      title={`Grade ${data.grade} · score ${data.score}. Open health report`}
    >
      <HeartPulse className="text-muted-foreground size-3.5" />
      <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 text-xs font-semibold">
        {data.grade}
      </span>
      {COUNTS.map(({ key, label, className }) => {
        const count = data.counts?.[key] ?? 0;
        if (count === 0) return null;
        return (
          <span
            key={key}
            className={`rounded px-1.5 py-0.5 text-xs font-medium tabular-nums ${className}`}
          >
            {count} {label}
          </span>
        );
      })}
    </Link>
  );
}
