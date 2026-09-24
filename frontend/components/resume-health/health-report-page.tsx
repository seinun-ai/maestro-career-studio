"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, HeartPulse, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  AskCard,
  COUNT_META,
  countWords,
  FixCard,
  FindingGroupHeader,
  GateBanner,
  GRADE_STYLES,
  NotesTable,
  ResolvedFinding,
} from "@/components/resume-health/finding-cards";
import { BatchAskDialog } from "@/components/resume-health/batch-ask-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/icon-button";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  apiFetch,
  getAskAnswers,
  getLintReport,
  overrideLevel,
  runLintReport,
} from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { isLoadFailure } from "@/lib/query-state";
import {
  addNumbersLabel,
  checkDoneWords,
  explainScoreDelta,
  filterFindings,
  groupFindings,
  groupTitle,
  healthCounts,
  isMetricAsk,
  leftToFix,
  reportInsufficientEvidence,
  reportIsStale,
  scoreCompositionLine,
  sharedCoaching,
  hoistBlurb,
  type StreamFilter,
  staleFindingIds,
} from "@/lib/health-report";
import { cn } from "@/lib/utils";
import type {
  BaseResumeDetail,
  EvidenceLevel,
  LintFinding,
  LintReport,
  ResumeData,
} from "@/lib/types";

const FILTERS: { id: StreamFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "fix", label: "Fixes" },
  { id: "ask", label: "Questions" },
  { id: "note", label: "Notes" },
];

// The career stage the score is judged against (`health_zones.compute_tier`).
// "unknown" (no dates to read) shows no badge: it is not a stage.
const TIER_LABELS: Record<string, string | undefined> = {
  early: "Early career",
  experienced: "Experienced",
};

const currentOf = (ref: RefObject<HTMLElement | null>) => ref.current;

/**
 * A block that can leave while it holds focus (the stale banner, the applied
 * bar, the first-check empty state: each holds a Check button and goes once the
 * check lands). Focus that was inside moves to `to`, the rail's Check again,
 * after the commit that removed the block, never to <body>.
 */
function FocusHandoff({
  to,
  className,
  children,
}: {
  to: RefObject<HTMLElement | null>;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // A LAYOUT cleanup: it runs before React detaches the block, while the
  // focused button is still inside it.
  useLayoutEffect(() => {
    const root = ref.current;
    return () => {
      if (!root?.contains(document.activeElement)) return;
      // Read after the commit on purpose: the target may be new in it (the
      // first check's report brings the rail's button with it).
      queueMicrotask(() => focusIfDropped(currentOf(to)));
    };
  }, [to]);
  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/**
 * Full-page resume health report. Header stays on the shared PageShell origin;
 * the body is a two-pane layout above 1024px (sticky rail + finding stream).
 * Prose measure lives inside cards (~65ch), not on the page.
 */
export function HealthReportPage({
  resumeKey,
  backHref,
  backLabel,
}: {
  resumeKey: string;
  backHref: string;
  backLabel: string;
}) {
  // The web report is base resumes only. A tailored resume inherits its base's
  // health score; MCP's health tools still accept kind="application".
  const kind = "base" as const;
  const qc = useQueryClient();
  const [filter, setFilter] = useState<StreamFilter>("all");
  const [appliedCount, setAppliedCount] = useState(0);
  const [scoreDelta, setScoreDelta] = useState<{
    fromGrade: string;
    fromScore: number;
    toGrade: string;
    toScore: number;
    explanation: string | null;
  } | null>(null);
  const [resolved, setResolved] = useState<LintFinding[]>([]);
  const [batchOpen, setBatchOpen] = useState(false);
  const priorFindings = useRef<LintFinding[]>([]);
  const priorScore = useRef<{ grade: string; score: number } | null>(null);

  const baseQuery = useQuery({
    queryKey: ["base-resumes", resumeKey],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${resumeKey}`),
  });

  const resumeData: ResumeData | null = baseQuery.data?.data ?? null;

  const templateId = baseQuery.data?.template_id ?? null;

  const label = useMemo(() => {
    const detail = baseQuery.data;
    return detail ? (detail.display_name ?? detail.slug) : null;
  }, [baseQuery.data]);

  const report = useQuery<LintReport>({
    queryKey: ["resume-lint", kind, resumeKey],
    queryFn: () => getLintReport(kind, resumeKey),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });

  const [staleIds, setStaleIds] = useState<Set<string>>(new Set());
  const reportData = report.data;
  const reportIsStaleNow = reportIsStale(reportData);
  useEffect(() => {
    // A stale report locks only the findings whose own text drifted; every
    // apply is hash-guarded server-side, so untouched bullets stay actionable.
    let cancelled = false;
    void (async () => {
      const ids =
        reportIsStaleNow && reportData && resumeData
          ? await staleFindingIds(reportData.findings, resumeData)
          : new Set<string>();
      if (!cancelled) setStaleIds(ids);
    })();
    return () => {
      cancelled = true;
    };
  }, [reportIsStaleNow, reportData, resumeData]);

  const answers = useQuery({
    queryKey: ["resume-lint", kind, resumeKey, "answers"],
    queryFn: () => getAskAnswers(kind, resumeKey),
  });

  const adoptReport = (result: LintReport, fromReanalyze: boolean) => {
    if (fromReanalyze && priorScore.current) {
      const delta = result.score - priorScore.current.score;
      if (delta !== 0 || result.grade !== priorScore.current.grade) {
        setScoreDelta({
          fromGrade: priorScore.current.grade,
          fromScore: priorScore.current.score,
          toGrade: result.grade,
          toScore: result.score,
          explanation: explainScoreDelta(
            priorFindings.current,
            result.findings,
            (key) => groupTitle(key, resumeData),
          ),
        });
      } else {
        setScoreDelta(null);
      }
      const nextIds = new Set(result.findings.map((f) => f.id));
      setResolved(
        priorFindings.current.filter(
          (f) => !nextIds.has(f.id) && f.type !== "note" && f.type !== "gate",
        ),
      );
    }
    priorFindings.current = result.findings;
    priorScore.current = { grade: result.grade, score: result.score };
    qc.setQueryData(["resume-lint", kind, resumeKey], result);
  };

  const analyze = useMutation({
    mutationFn: () => runLintReport(kind, resumeKey),
    onSuccess: (result) => {
      adoptReport(result, Boolean(report.data));
      setAppliedCount(0);
      // "Too little to grade" in the rail: the toast never names a grade.
      toast.success(checkDoneWords(result));
    },
    onError: (err: Error) => toast.error(couldnt("check the resume", err)),
  });
  // One check per gesture: a double click ran the check twice.
  const analyzeOnce = useSingleFlight(analyze.mutate);
  // The rail's Check again: where focus goes when a block holding another
  // Check button leaves.
  const checkRef = useRef<HTMLButtonElement>(null);

  // The report's failure, remembered through a retry: a 404 is "No health report yet", anything
  // else is the error with its Try again. Both render ahead of the loading gate below, because a
  // retry puts a data-less query back into `isLoading` and the skeleton unmounted the focused button.
  const reportError = useLoadFailureError(report);
  const noReportYet = reportError instanceof ApiError && reportError.status === 404;
  const reportFailed = reportError != null && !noReportYet;

  useEffect(() => {
    if (!report.data || priorScore.current) return;
    priorFindings.current = report.data.findings;
    priorScore.current = { grade: report.data.grade, score: report.data.score };
  }, [report.data]);

  const reanalyzeReport = async () => {
    const result = await runLintReport(kind, resumeKey);
    adoptReport(result, true);
    setAppliedCount(0);
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
    adoptReport(result, true);
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

  const invalidateAfterApply = () => {
    setAppliedCount((n) => n + 1);
    void qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey, "answers"] });
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["resume-versions"] });
    qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey] });
  };

  if (isLoadFailure(baseQuery)) {
    return (
      <PageShell>
        <LoadErrorState
          title="Couldn't load this resume."
          detail={loadErrorDetail(baseQuery.error, "resume")}
          retrying={baseQuery.isFetching}
          onRetry={() => void baseQuery.refetch()}
          action={
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href={backHref}>Back</Link>}
            />
          }
        />
      </PageShell>
    );
  }

  if (baseQuery.isLoading || (report.isLoading && reportError == null)) {
    return (
      <PageShell>
        <Skeleton className="h-10 w-60" />
        <Skeleton className="h-96 w-full" />
      </PageShell>
    );
  }

  const body = report.data;
  const stale = reportIsStale(body);
  const insufficient = reportInsufficientEvidence(body);
  const gates = body?.gates ?? [];
  const findings = body?.findings.filter((f) => f.type !== "gate") ?? [];
  const notes = findings.filter((f) => f.type === "note");
  const nonNote = findings.filter((f) => f.type !== "note");
  const metricAsks = nonNote.filter(
    (f) => f.type === "ask" && isMetricAsk(f.question),
  );
  const visibleNonNote =
    filter === "note" ? [] : filterFindings(nonNote, filter);
  const groups = groupFindings(visibleNonNote);
  const nScoreable = body?.score_breakdown?.n_scoreable ?? null;
  const composition = body
    ? scoreCompositionLine(body.score, body.score_breakdown, gates)
    : null;
  // One count per tier on every surface: "must fix" is failed fatal checks only.
  const counts = body ? healthCounts(body) : {};
  const showNotes = filter === "all" || filter === "note";
  const showFixes = filter !== "note";
  const hasBannerGate = gates.some(
    (g) => g.status === "fail" || g.status === "waived" || g.status === "not_assessed",
  );
  const hasAnything = hasBannerGate || findings.length > 0;

  const jumpItems = [
    // The rows under "Checks": failed, unchecked and marked-OK checks.
    ...(hasBannerGate
      ? [{ id: "gates", label: "Checks", count: gates.filter((g) => g.status !== "pass").length }]
      : []),
    ...groups.map((g) => ({
      id: `group-${g.key}`,
      label: groupTitle(g.key, resumeData),
      count: g.findings.length,
    })),
    ...(notes.length > 0 ? [{ id: "notes", label: "Notes", count: notes.length }] : []),
  ];

  const remaining = leftToFix(counts, nonNote.length);
  const analyzeButton = (ref?: RefObject<HTMLButtonElement | null>) => (
    <Button
      ref={ref}
      size="sm"
      variant={body ? "outline" : "default"}
      disabled={analyze.isPending}
      onClick={() => analyzeOnce()}
      // Disables itself while checking: a native `disabled` drops focus.
      focusableWhenDisabled
      className="data-disabled:pointer-events-none data-disabled:opacity-50"
    >
      {analyze.isPending ? (
        <Loader2 className="mr-1 size-3.5 animate-spin" />
      ) : (
        <RefreshCw className="mr-1 size-3.5" />
      )}
      {analyze.isPending ? "Checking…" : body ? "Check again" : "Check health"}
    </Button>
  );

  return (
    <PageShell>
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
            <HeartPulse className="size-5" /> Health report
          </span>
        }
        subtitle={label}
      />

      {reportFailed ? (
        <LoadErrorState
          title="Couldn't load this health report."
          detail={loadErrorDetail(reportError)}
          retrying={report.isFetching}
          onRetry={() => void report.refetch()}
        />
      ) : body ? (
        <div className="grid items-start gap-6 lg:grid-cols-[18.75rem_minmax(0,1fr)]">
          <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
            <section className="flex flex-col gap-3 rounded-lg border p-4">
              <div className="flex items-center gap-3">
                {insufficient ? (
                  <span className="text-muted-foreground flex size-14 items-center justify-center rounded-lg text-center text-[10px] leading-tight font-medium">
                    Too little to grade
                  </span>
                ) : (
                  <span
                    className={cn(
                      "flex size-14 items-center justify-center rounded-lg text-3xl font-bold",
                      GRADE_STYLES[body.grade] ?? GRADE_STYLES.C,
                    )}
                  >
                    {body.grade}
                  </span>
                )}
                <div className="flex min-w-0 flex-col gap-1">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      insufficient && "text-muted-foreground",
                    )}
                  >
                    {body.score}/100
                  </span>
                  {scoreDelta && (
                    <div className="space-y-0.5">
                      <p className="text-xs">
                        {scoreDelta.fromGrade} {scoreDelta.fromScore} →{" "}
                        {scoreDelta.toGrade} {scoreDelta.toScore}
                        {scoreDelta.toScore - scoreDelta.fromScore !== 0 && (
                          <span className="text-muted-foreground">
                            {", "}
                            {scoreDelta.toScore - scoreDelta.fromScore > 0 ? "+" : ""}
                            {scoreDelta.toScore - scoreDelta.fromScore}
                          </span>
                        )}
                      </p>
                      {scoreDelta.explanation && (
                        <p className="text-muted-foreground text-xs">
                          {scoreDelta.explanation}
                        </p>
                      )}
                    </div>
                  )}
                  {body.tier && TIER_LABELS[body.tier] && (
                    <Badge variant="secondary" className="w-fit text-xs">
                      {TIER_LABELS[body.tier]}
                    </Badge>
                  )}
                </div>
              </div>
              {composition && (
                <p className="text-muted-foreground text-xs">{composition}</p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {COUNT_META.map(({ key, chip }) => {
                  const count = counts[key] ?? 0;
                  if (count === 0) return null;
                  return (
                    <Badge
                      key={key}
                      variant="secondary"
                      className={cn("text-xs", chip)}
                    >
                      {countWords(key, count)}
                    </Badge>
                  );
                })}
              </div>
              <p className="text-muted-foreground text-xs">
                {remaining} left to fix
                {body.resume_version_number != null &&
                  ` · Version ${body.resume_version_number}`}
              </p>
            </section>

            {jumpItems.length > 0 && (
              <nav aria-label="Report sections" className="flex flex-col gap-1">
                {jumpItems.map((item) => (
                  <a
                    key={item.id}
                    href={`#${item.id}`}
                    className="text-muted-foreground hover:text-foreground flex items-center justify-between rounded-md px-2 py-1 text-xs"
                  >
                    <span className="truncate">{item.label}</span>
                    <span>{item.count}</span>
                  </a>
                ))}
              </nav>
            )}

            {/* The tonal fill is quiet (about 1.16:1 against the light
                page), so the check says "selected", as on M3's selected
                filter chip. */}
            <div className="flex flex-wrap gap-1.5">
              {FILTERS.map((f) => (
                <Button
                  key={f.id}
                  size="xs"
                  variant={filter === f.id ? "tonal" : "outline"}
                  aria-pressed={filter === f.id}
                  onClick={() => setFilter(f.id)}
                >
                  {filter === f.id && <Check />}
                  {f.label}
                </Button>
              ))}
            </div>

            {metricAsks.length > 0 && resumeData && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setBatchOpen(true)}
              >
                {addNumbersLabel(metricAsks.length)}
              </Button>
            )}
            {analyzeButton(checkRef)}
          </aside>

          <div className="flex min-w-0 flex-col gap-6">
            {stale && (
              <FocusHandoff to={checkRef} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
                <p>Your resume changed since this check. Check again to update it.</p>
                {analyzeButton()}
              </FocusHandoff>
            )}

            <GateBanner
              gates={gates}
              kind={kind}
              resumeKey={resumeKey}
              onChanged={reanalyzeReport}
              templateId={templateId}
            />

            {!hasAnything && (
              <p className="text-sm">No issues found.</p>
            )}

            {showFixes && visibleNonNote.length > 0 && resumeData == null && (
              <p className="text-muted-foreground max-w-[65ch] text-sm">
                Couldn&apos;t load your resume text. Open the resume to fix
                these.
              </p>
            )}

            {showFixes && visibleNonNote.length > 0 && resumeData != null && (
              <section className="space-y-4">
                <h2 className="text-sm font-medium">Biggest problems first</h2>
                {groups.map((group) => (
                  <div key={group.key} className="space-y-2">
                    <FindingGroupHeader
                      id={`group-${group.key}`}
                      title={groupTitle(group.key, resumeData)}
                      findings={group.findings}
                    />
                    {group.findings.map((finding) => {
                      const hideHow = Boolean(
                        hoistBlurb(group.findings) || sharedCoaching(group.findings),
                      );
                      return finding.type === "ask" ? (
                        <AskCard
                          key={finding.id}
                          finding={finding}
                          data={resumeData}
                          kind={kind}
                          resumeKey={resumeKey}
                          onApplied={invalidateAfterApply}
                          onClassificationChanged={overrideClassification}
                          onReanalyze={() => void reanalyzeReport()}
                          locked={stale && staleIds.has(finding.id)}
                          nScoreable={nScoreable}
                          hideHow={hideHow}
                          storedAnswer={answers.data?.[finding.id]}
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
                          onReanalyze={() => void reanalyzeReport()}
                          locked={stale && staleIds.has(finding.id)}
                          nScoreable={nScoreable}
                          hideHow={hideHow}
                        />
                      );
                    })}
                  </div>
                ))}
              </section>
            )}

            {resolved.length > 0 && (
              <div className="space-y-2">
                {resolved.map((finding) => (
                  <ResolvedFinding key={finding.id} finding={finding} />
                ))}
              </div>
            )}

            {/* Hidden, not unmounted, when the filter leaves notes out: it
                holds the kept Demonstrate-skill drafts. */}
            {notes.length > 0 && (
              <NotesTable
                hidden={!showNotes}
                notes={notes}
                data={resumeData}
                kind={kind}
                resumeKey={resumeKey}
                onApplied={invalidateAfterApply}
                locked={false}
                onReanalyze={() => void reanalyzeReport()}
              />
            )}
          </div>
        </div>
      ) : (
        // Kept while the first check runs: its button holds the focus
        // (showing "Checking…") until the report replaces it.
        noReportYet && (
          <FocusHandoff to={checkRef} className="flex flex-col items-start gap-3">
            <p className="text-muted-foreground max-w-[65ch] text-sm">
              No health report yet. This checks your resume on its own, without a
              job description.
            </p>
            {analyzeButton()}
          </FocusHandoff>
        )
      )}

      {appliedCount > 0 && (
        <FocusHandoff to={checkRef} className="bg-background/95 sticky bottom-4 z-20 flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm shadow-sm">
          <p>
            {appliedCount} {appliedCount === 1 ? "change" : "changes"} applied.
            Check again to update your grade.
          </p>
          {analyzeButton()}
        </FocusHandoff>
      )}
      {batchOpen && resumeData && (
        <BatchAskDialog
          open={batchOpen}
          onOpenChange={setBatchOpen}
          findings={metricAsks}
          data={resumeData}
          kind={kind}
          resumeKey={resumeKey}
          locked={false}
          staleIds={staleIds}
          storedAnswers={answers.data}
          onApplied={invalidateAfterApply}
          onReanalyze={() => void reanalyzeReport()}
        />
      )}
    </PageShell>
  );
}
