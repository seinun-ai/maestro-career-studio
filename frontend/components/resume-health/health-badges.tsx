"use client";

import { GuardedLink as Link } from "@/components/guarded-link";
import { useQuery } from "@tanstack/react-query";
import { HeartPulse } from "lucide-react";

import { RetryChip } from "@/components/retry-chip";
import { COUNT_META, countWords, GRADE_STYLES } from "@/components/resume-health/finding-cards";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { ApiError, apiFetch, getLintReport } from "@/lib/api";
import { fatalGateFailed } from "@/lib/health-report";
import { cn } from "@/lib/utils";

type LintReport = {
  score: number;
  grade: string;
  counts: Record<string, number>;
  created_at: string;
};

/**
 * "2 must fix, 8 questions", worst first, skipping severities with nothing in
 * them, or "No issues" when a report came back with every severity at zero.
 */
function summarizeCounts(counts: Record<string, number> | undefined): string {
  const parts = COUNT_META.flatMap(({ key }) => {
    const count = counts?.[key] ?? 0;
    return count === 0 ? [] : [countWords(key, count)];
  });
  return parts.length === 0 ? "No issues" : parts.join(", ");
}

/**
 * The editor header's single health entry point: a link to the full-page
 * report. When a report exists it shows one grade chip — the per-severity
 * counts live in its tooltip, and in full on the report it links to, rather
 * than as a row of chips camped in the header. Otherwise a compact "Check
 * health" link keeps the report (and its Analyze CTA) discoverable.
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
  const report = useQuery({
    queryKey: ["resume-lint", kind, resumeKey],
    queryFn: () =>
      apiFetch<LintReport>(`/api/resume-lint/${kind}/${resumeKey}`),
    retry: false,
    staleTime: 60_000,
  });
  const data = report.data;
  // Remembered through a retry, so the chip stays mounted (and focused) while
  // it runs; a 404 is "never analyzed", the Check health link below.
  const failure = useLoadFailureError(report);

  // Both states share the same bordered pill so health reads as one control in
  // the header row rather than loose chips floating between the buttons — it
  // was easy to miss entirely at a glance.
  const shell =
    "hover:bg-muted/60 hover:border-border flex items-center gap-1.5 rounded-md " +
    "border border-transparent bg-muted/40 px-2 py-1 transition-colors";

  const missing = failure instanceof ApiError && failure.status === 404;
  if (failure != null && !missing) {
    return (
      <RetryChip
        className={`${shell} text-muted-foreground hover:text-foreground text-sm`}
        title="Couldn't check this resume's health. Try again."
        icon={<HeartPulse className="size-4" />}
        label="Couldn't check health"
        retrying={report.isFetching}
        onRetry={() => void report.refetch()}
      />
    );
  }

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

  // The counts only live in the tooltip now, and a tooltip is mouse-only —
  // aria-label carries the same sentence to screen readers and touch.
  const summary =
    `Grade ${data.grade}, score ${data.score}. ` +
    `${summarizeCounts(data.counts)}. Open report.`;

  return (
    <Link
      href={reportHref}
      className={shell}
      title={summary}
      aria-label={summary}
    >
      <HeartPulse className="text-muted-foreground size-3.5" />
      {/* The word makes the grade legible: a bare letter beside the KB pill
          read as noise, and only hover/AT channels said "health". */}
      <span className="text-muted-foreground text-sm">Health</span>
      {/* Same grade palette as the report page: the chip is the header's only
          severity signal now, so an F must not read like an A. */}
      <span
        className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
          GRADE_STYLES[data.grade] ?? GRADE_STYLES.C
        }`}
      >
        {data.grade}
      </span>
    </Link>
  );
}

/**
 * Compact grade chip for a Base resumes gallery row. 404 → render nothing
 * (this base has never been analyzed). A failing fatal gate is "Must fix" —
 * the state that otherwise first appears as a tailoring 409.
 */
export function HealthListChip({ slug }: { slug: string }) {
  const { data, isError, error } = useQuery({
    queryKey: ["resume-lint", "base", slug],
    queryFn: () => getLintReport("base", slug),
    retry: false,
    staleTime: 60_000,
  });

  const missing = error instanceof ApiError && error.status === 404;
  if ((isError && missing) || isError || !data) return null;

  const blocked = fatalGateFailed(data.gates);
  const summary = blocked
    ? "Has a must-fix problem. Open the report."
    : `Grade ${data.grade}, score ${data.score}. Open report.`;

  return (
    <Link
      href={`/base-resumes/${slug}/health`}
      className={cn(
        "relative z-20 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold",
        blocked
          ? "bg-destructive/10 text-destructive"
          : (GRADE_STYLES[data.grade] ?? GRADE_STYLES.C),
      )}
      title={summary}
      aria-label={summary}
      onClick={(event) => event.stopPropagation()}
    >
      {blocked ? "Must fix" : data.grade}
    </Link>
  );
}
