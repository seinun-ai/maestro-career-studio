"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, HeartPulse, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  AskCard,
  COUNT_META,
  FixCard,
  GateBanner,
  GRADE_STYLES,
  NoteItem,
} from "@/components/resume-health/finding-cards";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/icon-button";
import { PageHeader, PageShell, PageMeasure } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  apiFetch,
  getLintReport,
  overrideLevel,
  runLintReport,
} from "@/lib/api";
import { resumeDataSchema } from "@/lib/resume-schema";
import { cn } from "@/lib/utils";
import type {
  ApplicationDetail,
  BaseResumeDetail,
  EvidenceLevel,
  LintReport,
  ResumeData,
} from "@/lib/types";

/**
 * Full-page resume health report — the single health surface, laid out as one
 * readable column. Shares query keys with the header badges (`["resume-lint",
 * kind, key]`) and with the editor pages' resume queries, so all surfaces stay
 * in sync through the react-query cache.
 */
export function HealthReportPage({
  kind,
  resumeKey,
  backHref,
  backLabel,
}: {
  kind: "base" | "application";
  resumeKey: string;
  /** Editor page to return to. */
  backHref: string;
  /** Fallback back-link text while the resume's own name is loading. */
  backLabel: string;
}) {
  const qc = useQueryClient();

  // Resume content, for source quotes + Apply ops. Same keys/fetchers as the
  // editor pages (base-resumes/[slug], applications/[id]/resume) so the cache
  // is shared with them.
  const baseQuery = useQuery({
    queryKey: ["base-resumes", resumeKey],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${resumeKey}`),
    enabled: kind === "base",
  });
  const appQuery = useQuery({
    queryKey: ["application", resumeKey],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${resumeKey}`),
    enabled: kind === "application",
  });
  const detailQuery = kind === "base" ? baseQuery : appQuery;

  const resumeData = useMemo<ResumeData | null>(() => {
    if (kind === "base") return baseQuery.data?.data ?? null;
    const raw = appQuery.data?.customized_json;
    if (raw == null) return null;
    const parsed = resumeDataSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  }, [kind, baseQuery.data, appQuery.data]);

  const label = useMemo(() => {
    if (kind === "base") {
      const detail = baseQuery.data;
      return detail ? (detail.display_name ?? detail.slug) : null;
    }
    const job = appQuery.data?.job;
    if (!job) return null;
    return job.title && job.company
      ? `${job.title} · ${job.company}`
      : (job.title ?? job.company ?? null);
  }, [kind, baseQuery.data, appQuery.data]);

  const report = useQuery<LintReport>({
    queryKey: ["resume-lint", kind, resumeKey],
    queryFn: () => getLintReport(kind, resumeKey),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const analyze = useMutation({
    mutationFn: () => runLintReport(kind, resumeKey),
    onSuccess: (result) => {
      qc.setQueryData(["resume-lint", kind, resumeKey], result);
      toast.success(`Analyzed. Grade ${result.grade}.`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const noReportYet =
    report.isError && report.error instanceof ApiError && report.error.status === 404;

  const reanalyzeReport = async () => {
    const result = await runLintReport(kind, resumeKey);
    qc.setQueryData(["resume-lint", kind, resumeKey], result);
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

  const overrideClassification = async (
    contentHash: string,
    level: EvidenceLevel | null,
    reason: string,
  ) => {
    await overrideLevel(contentHash, level, reason);
    const result = await runLintReport(kind, resumeKey);
    qc.setQueryData(["resume-lint", kind, resumeKey], result);
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

  const invalidateAfterApply = () => {
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["application"] });
    qc.invalidateQueries({ queryKey: ["resume-versions"] });
    qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey] });
  };

  if (detailQuery.isError) {
    return (
      <PageShell>
        <p className="text-destructive">
          {kind === "base"
            ? "Failed to load resume."
            : "Failed to load application."}
        </p>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href={backHref}>Back</Link>}
        />
      </PageShell>
    );
  }

  if (detailQuery.isLoading || report.isLoading) {
    return (
      <PageShell>
        <Skeleton className="h-10 w-60" />
        <Skeleton className="h-96 w-full" />
      </PageShell>
    );
  }

  const body = report.data;
  const gates = body?.gates ?? [];
  const findings = body?.findings.filter((f) => f.type !== "gate") ?? [];
  const notes = findings.filter((f) => f.type === "note");
  const nonNote = findings.filter((f) => f.type !== "note");
  const hasBannerGate = gates.some(
    (g) => g.status === "fail" || g.status === "waived",
  );
  const hasAnything = hasBannerGate || (body?.findings.length ?? 0) > 0;

  return (
    <PageShell>
      {/* Header sits at the shared origin; only the BODY takes the ~65ch
          reading measure. Narrowing the shell to max-w-3xl was what pulled this
          page's title inward from every other route's. */}
      <PageHeader
        leading={
          <IconButton
            label={`Back to ${label ?? backLabel}`}
            icon={<ArrowLeft className="size-4" />}
            size="icon-sm"
            className="mt-1.5 shrink-0"
            nativeButton={false}
            render={<Link href={backHref} className="text-muted-foreground" />}
          />
        }
        title={
          <span className="flex items-center gap-2">
            <HeartPulse className="size-5" /> Resume health report
          </span>
        }
        subtitle={label}
        actions={
          <Button
            size="sm"
            variant={body ? "outline" : "default"}
            disabled={analyze.isPending}
            onClick={() => analyze.mutate()}
          >
            {analyze.isPending ? (
              <Loader2 className="mr-1 size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 size-3.5" />
            )}
            {analyze.isPending ? "Analyzing…" : body ? "Re-analyze" : "Analyze"}
          </Button>
        }
      />

      {/* Reading measure on the BODY, not the shell — findings are prose. */}
      <PageMeasure>
      {body ? (
        <>
          <section className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
            <span
              className={cn(
                "flex size-14 items-center justify-center rounded-lg text-3xl font-bold",
                GRADE_STYLES[body.grade] ?? GRADE_STYLES.C,
              )}
            >
              {body.grade}
            </span>
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{body.score}/100</span>
                {body.tier && (
                  <Badge variant="secondary" className="text-xs">
                    {body.tier}
                  </Badge>
                )}
                {COUNT_META.map(({ key, label: countLabel, chip }) => {
                  const count = body.counts?.[key] ?? 0;
                  if (count === 0) return null;
                  return (
                    <Badge
                      key={key}
                      variant="secondary"
                      className={cn("text-xs", chip)}
                    >
                      {count} {countLabel}
                    </Badge>
                  );
                })}
              </div>
              <p className="text-muted-foreground text-xs">
                Analyzed {new Date(body.created_at).toLocaleString()}
                {body.resume_version_number != null &&
                  ` · resume v${body.resume_version_number}`}
                {body.model && ` · ${body.model}`}
              </p>
            </div>
          </section>

          <GateBanner
            gates={gates}
            kind={kind}
            resumeKey={resumeKey}
            onChanged={reanalyzeReport}
          />

          {!hasAnything && (
            <p className="text-sm">No issues found. This resume looks solid.</p>
          )}

          {nonNote.length > 0 && resumeData == null && (
            <p className="text-muted-foreground text-sm">
              The resume content couldn&apos;t be loaded, so findings can&apos;t
              be shown with their source text here. Open the editor to work
              through them.
            </p>
          )}

          {nonNote.length > 0 && resumeData != null && (
            <section className="space-y-2">
              <h2 className="text-sm font-medium">
                What it&apos;s costing you, in order
              </h2>
              {nonNote.map((finding) =>
                finding.type === "ask" ? (
                  <AskCard
                    key={finding.id}
                    finding={finding}
                    data={resumeData}
                    kind={kind}
                    resumeKey={resumeKey}
                    onApplied={invalidateAfterApply}
                    onClassificationChanged={overrideClassification}
                  />
                ) : (
                  <FixCard
                    key={finding.id}
                    finding={finding}
                    data={resumeData}
                    kind={kind}
                    resumeKey={resumeKey}
                    onApplied={invalidateAfterApply}
                    onClassificationChanged={overrideClassification}
                  />
                ),
              )}
            </section>
          )}

          {notes.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-muted-foreground text-sm font-medium">
                No score impact ({notes.length})
              </h2>
              {notes.map((finding) => (
                <NoteItem
                  key={finding.id}
                  finding={finding}
                  data={resumeData ?? undefined}
                  onClassificationChanged={overrideClassification}
                />
              ))}
            </section>
          )}
        </>
      ) : (
        noReportYet &&
        !analyze.isPending && (
          <p className="text-muted-foreground text-sm">
            No health report yet. Run an analysis to check this resume against
            general best practices. No job description needed.
          </p>
        )
      )}
      </PageMeasure>
    </PageShell>
  );
}
