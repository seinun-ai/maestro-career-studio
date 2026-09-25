"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { flushSync } from "react-dom";
import { useSearchParams } from "next/navigation";
import { GuardedLink as Link } from "@/components/guarded-link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, HeartPulse, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  AskCard,
  FixCard,
  FindingGroupHeader,
  GateBanner,
  GRADE_STYLES,
  NotesTable,
  ResolvedFinding,
  ShortenList,
} from "@/components/resume-health/finding-cards";
import { DoneTab } from "@/components/resume-health/done-tab";
import { LoadErrorState } from "@/components/load-error-state";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { IconButton } from "@/components/icon-button";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  apiFetch,
  getAskAnswers,
  getDisputes,
  getLintReport,
  overrideLevel,
  reopenDispute,
  runLintReport,
} from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { focusIfStranded } from "@/lib/focus";
import { formatAbsoluteDateTime, formatTimeAgo } from "@/lib/format-date";
import { isLoadFailure } from "@/lib/query-state";
import {
  actionTabOf,
  checkDoneWords,
  checkedWords,
  defaultHealthTab,
  disputeChangedRating,
  explainScoreDelta,
  findingsByTab,
  groupTitle,
  hasOpenRating,
  healthCounts,
  HEALTH_TABS,
  leftToFix,
  liftedDispute,
  nextGradeLine,
  nextGradeProgress,
  NO_NUMBERS_RULE,
  parseHealthTab,
  reportInsufficientEvidence,
  reportIsStale,
  resolvedFindings,
  ruleGroups,
  scoreCompositionLine,
  sharedCoaching,
  staleFindingIds,
  textAtLocation,
  type ActionTab,
  type HealthTab,
} from "@/lib/health-report";
import { cn } from "@/lib/utils";
import type {
  BaseResumeDetail,
  DisputeResult,
  EvidenceLevel,
  LintFinding,
  LintReport,
  ResumeData,
} from "@/lib/types";

const TIER_LABELS: Record<string, string | undefined> = {
  early: "Early career",
  experienced: "Experienced",
};

const currentOf = (ref: RefObject<HTMLElement | null>) => ref.current;

/**
 * A block that can leave while it holds focus (the stale banner, the applied
 * bar, the first-check empty state: each holds a Check button and goes once the
 * check lands). Focus that was inside moves to `to`, the header's Check again,
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
      // first check's report brings the header's button with it).
      queueMicrotask(() => focusIfDropped(currentOf(to)));
    };
  }, [to]);
  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/** The findings a tab lists as cards (questions and rewrites); Shorten, Notes and Done have their own. */
const CARD_TABS: ActionTab[] = ["number", "detail", "reword"];

/**
 * Full-page resume health report: the header (with when it was checked and a quiet Check again), a
 * full-width summary band holding the grade and the page's one filled button, the checks, then one
 * tab per kind of action (owner decision 8: no left rail). Prose measure lives inside cards (~65ch).
 */
export function HealthReportPage({
  resumeKey,
  backHref,
  backLabel,
  questionsHref,
}: {
  resumeKey: string;
  backHref: string;
  backLabel: string;
  /** The question pass, which "Start the questions" opens. */
  questionsHref: string;
}) {
  // The web report is base resumes only. A tailored resume inherits its base's
  // health score; MCP's health tools still accept kind="application".
  const kind = "base" as const;
  const qc = useQueryClient();
  const [appliedCount, setAppliedCount] = useState(0);
  const [scoreDelta, setScoreDelta] = useState<{
    fromGrade: string;
    fromScore: number;
    toGrade: string;
    toScore: number;
    explanation: string | null;
  } | null>(null);
  const [resolved, setResolved] = useState<LintFinding[]>([]);
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
      setResolved(resolvedFindings(priorFindings.current, result.findings));
    }
    priorFindings.current = result.findings;
    priorScore.current = { grade: result.grade, score: result.score };
    qc.setQueryData(["resume-lint", kind, resumeKey], result);
  };

  // Re-runs can be asked for while one runs (two quick Ignores, a Check again during a dispute's
  // re-run). They run ONE AT A TIME, queued: the server saves each report when its run finishes and
  // serves the newest by that time, so two overlapping runs could leave an older report as its
  // latest. Each request is also numbered, and a report older than the last one adopted is dropped.
  const runQueue = useRef<Promise<unknown>>(Promise.resolve());
  const runSeq = useRef(0);
  const adoptedSeq = useRef(0);
  const runLatest = async (): Promise<LintReport | null> => {
    const seq = ++runSeq.current;
    // The queue never rejects: a failed run fails its own caller and lets the next one start.
    const turn = runQueue.current.then(() => runLintReport(kind, resumeKey));
    runQueue.current = turn.catch(() => undefined);
    const result = await turn;
    if (seq < adoptedSeq.current) return null;
    adoptedSeq.current = seq;
    return result;
  };

  const analyze = useMutation({
    mutationFn: runLatest,
    onSuccess: (result) => {
      if (!result) return;
      adoptReport(result, Boolean(report.data));
      setAppliedCount(0);
      // "Too little to grade" in the band: the toast never names a grade.
      toast.success(checkDoneWords(result));
    },
    onError: (err: Error) => toast.error(couldnt("check the resume", err)),
  });
  // One check per gesture: a double click ran the check twice.
  const analyzeOnce = useSingleFlight(analyze.mutate);
  // The header's Check again: where focus goes when a block holding another
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
    setLastDisputed(null);
    const result = await runLatest();
    if (!result) return;
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
    setLastDisputed(null);
    const result = await runLatest();
    if (!result) return;
    adoptReport(result, true);
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

  // The latest "Not right?" reply per bullet (content hash). Kept here, not in the card: a dispute
  // that moves the rating runs the report again, which can replace the card with a new one.
  const [disputes, setDisputes] = useState<Record<string, DisputeResult>>({});
  // The bullet of a dispute whose re-run may replace its card: the card mounting on it opens on the
  // reply. Its landing or collapse clears it, as does any other action (Check again, an override,
  // an Apply).
  const [lastDisputed, setLastDisputed] = useState<string | null>(null);
  // Bullets a dispute's own re-run lifted out of the report: their Fixed entry carries the reply.
  const [lifted, setLifted] = useState<ReadonlySet<string>>(new Set());
  const afterDispute = async (result: DisputeResult) => {
    const hash = result.content_hash;
    setDisputes((d) => ({ ...d, [hash]: result }));
    if (!disputeChangedRating(result)) return;
    setLastDisputed(hash);
    const fresh = await runLatest();
    if (!fresh) return;
    adoptReport(fresh, true);
    if (!hasOpenRating(fresh.findings, hash)) setLifted((l) => new Set(l).add(hash));
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

  // What the user marked not right, for the Done tab (every re-run's invalidation refetches it).
  const storedDisputes = useQuery({
    queryKey: ["resume-lint", kind, resumeKey, "disputes"],
    queryFn: () => getDisputes(kind, resumeKey),
  });
  // Reopen (the Done tab): the rating is the check's own again, so the kept reply goes with it.
  const reopen = async (hash: string) => {
    await reopenDispute(hash);
    setDisputes((d) => Object.fromEntries(Object.entries(d).filter(([key]) => key !== hash)));
    await reanalyzeReport();
  };

  // Disputes are never dropped on Apply: the applied editor stays on screen with its "Applied" (and
  // the focus) until the next report, whose new text matches no stored dispute. A stale reply never
  // reaches a Fixed entry, which shows only a bullet its own dispute lifted.
  const invalidateAfterApply = () => {
    setLastDisputed(null);
    setAppliedCount((n) => n + 1);
    void qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey, "answers"] });
    qc.invalidateQueries({ queryKey: ["base-resumes"] });
    qc.invalidateQueries({ queryKey: ["resume-versions"] });
    qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey] });
  };

  // The open tab. `?tab=` is read with useSearchParams (the page keeps `use(searchParams)`, SYSTEM.md
  // §12: the prop keeps its arrival value after a native replaceState). With none, the tab whose
  // findings gain the most, chosen once, when the first report arrives: a re-run never moves the
  // user to another tab.
  const urlTab = parseHealthTab(useSearchParams().get("tab"));
  const [picked, setPicked] = useState<HealthTab | null>(urlTab);
  const [seenUrl, setSeenUrl] = useState(urlTab);
  if (seenUrl !== urlTab) {
    setSeenUrl(urlTab);
    if (urlTab) setPicked(urlTab);
  }
  if (picked == null && report.data) setPicked(defaultHealthTab(report.data.findings));
  const tab: HealthTab = picked ?? "notes";
  // A click writes the URL with the NATIVE replaceState, as the settings tabs do: no server round
  // trip, no history entry, and a reload opens what is on screen.
  const selectTab = (next: HealthTab) => {
    setPicked(next);
    window.history.replaceState(null, "", `${window.location.pathname}?tab=${next}`);
  };
  // A tab opened by anything but the tab row (Back to a `?tab=` entry) can hide the panel holding
  // focus; the open panel takes it. A layout effect: inert blurs only at the next focus fixup.
  const shownTab = useRef(tab);
  useLayoutEffect(() => {
    if (shownTab.current === tab) return;
    shownTab.current = tab;
    focusIfStranded(document.querySelector<HTMLElement>(`[data-health-tab="${tab}"]`));
  }, [tab]);

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
  const tabs = findingsByTab(findings);
  // "No numbers anywhere": the band's highlighted callout, never a note in a tab.
  const noNumbers = findings.find((f) => f.rule === NO_NUMBERS_RULE) ?? null;
  const askCount = findings.filter((f) => f.type === "ask").length;
  const overrides = findings.filter(
    (f) => f.content_hash != null && f.classification_source === "override",
  );
  const disputeRows = storedDisputes.data ?? [];
  const marked = disputeRows.length;
  const countOf = (id: HealthTab) =>
    id === "done" ? resolved.length + disputeRows.length + overrides.length : tabs[id].length;
  const nScoreable = body?.score_breakdown?.n_scoreable ?? null;
  const composition = body
    ? scoreCompositionLine(body.score, body.score_breakdown, gates)
    : null;
  const progress = body && !insufficient ? nextGradeProgress(body) : null;
  // One count per tier on every surface: "must fix" is failed fatal checks only.
  const counts = body ? healthCounts(body) : {};
  const hasBannerGate = gates.some(
    (g) => g.status === "fail" || g.status === "waived" || g.status === "not_assessed",
  );
  const hasAnything = hasBannerGate || findings.some((f) => f !== noNumbers);
  const remaining = leftToFix(
    counts,
    findings.filter((f) => f.type === "fix" || f.type === "ask").length,
  );

  // The callout's link opens the tab and moves focus into it (the link itself stays, so focus has
  // not dropped: it is moved on purpose, after the commit that shows the panel).
  const openTab = (id: HealthTab) => {
    flushSync(() => selectTab(id));
    document.querySelector<HTMLElement>(`[data-health-tab="${id}"]`)?.focus();
  };

  const analyzeButton = () => (
    <Button
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

  const renderFinding = (finding: LintFinding, hideHow: boolean) =>
    finding.type === "ask" ? (
      <AskCard
        key={finding.id}
        finding={finding}
        data={resumeData!}
        kind={kind}
        resumeKey={resumeKey}
        onApplied={invalidateAfterApply}
        onClassificationChanged={overrideClassification}
        dispute={finding.content_hash ? disputes[finding.content_hash] : undefined}
        disputeFresh={finding.content_hash != null && finding.content_hash === lastDisputed}
        onDisputeSeen={() => setLastDisputed(null)}
        onDisputed={afterDispute}
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
        data={resumeData!}
        kind={kind}
        resumeKey={resumeKey}
        onApplied={invalidateAfterApply}
        onClassificationChanged={overrideClassification}
        dispute={finding.content_hash ? disputes[finding.content_hash] : undefined}
        disputeFresh={finding.content_hash != null && finding.content_hash === lastDisputed}
        onDisputeSeen={() => setLastDisputed(null)}
        onDisputed={afterDispute}
        onReanalyze={() => void reanalyzeReport()}
        locked={stale && staleIds.has(finding.id)}
        nScoreable={nScoreable}
        hideHow={hideHow}
      />
    );

  const nothingHere = <p className="text-muted-foreground text-sm">Nothing to do here.</p>;
  const noResumeText = (
    <p className="text-muted-foreground max-w-[65ch] text-sm">
      Couldn&apos;t load your resume text. Open the resume to fix these.
    </p>
  );

  // A card tab: its rows grouped by the rule they break, each rule stated once; then the Fixed entry
  // of any bullet a dispute lifted out of this tab, carrying the reply (and the focus).
  const cardTab = (id: ActionTab) => (
    <>
      {tabs[id].length === 0
        ? nothingHere
        : resumeData == null
          ? noResumeText
          : ruleGroups(tabs[id]).map((group) => (
              <div key={group.key} className="space-y-2">
                <FindingGroupHeader
                  id={`group-${id}-${group.key}`}
                  title={group.title}
                  findings={group.findings}
                  nScoreable={nScoreable}
                />
                {group.findings.map((finding) =>
                  renderFinding(finding, Boolean(sharedCoaching(group.findings))),
                )}
              </div>
            ))}
      {resolved
        .filter(
          (finding) =>
            actionTabOf(finding) === id && liftedDispute(finding, lifted, disputes) != null,
        )
        .map((finding) => (
          <ResolvedFinding
            key={finding.id}
            finding={finding}
            dispute={liftedDispute(finding, lifted, disputes)}
            currentText={resumeData ? textAtLocation(resumeData, finding) : null}
          />
        ))}
    </>
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
        subtitle={
          <span className="flex flex-wrap items-center gap-x-1.5">
            {label && <span className="break-words">{label}</span>}
            {body && (
              <>
                {label && <span aria-hidden>·</span>}
                <span title={formatAbsoluteDateTime(body.created_at)}>
                  {checkedWords(formatTimeAgo(body.created_at), body.resume_version_number)}
                </span>
                <IconButton
                  ref={checkRef}
                  label={analyze.isPending ? "Checking…" : "Check again"}
                  icon={
                    analyze.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )
                  }
                  size="icon-xs"
                  disabled={analyze.isPending}
                  // Disables itself while checking: a native `disabled` drops focus.
                  focusableWhenDisabled
                  className="data-disabled:pointer-events-none data-disabled:opacity-50"
                  onClick={() => analyzeOnce()}
                />
              </>
            )}
          </span>
        }
      />

      {reportFailed ? (
        <LoadErrorState
          title="Couldn't load this health report."
          detail={loadErrorDetail(reportError)}
          retrying={report.isFetching}
          onRetry={() => void report.refetch()}
        />
      ) : body ? (
        <div className="flex min-w-0 flex-col gap-6">
          <section
            data-summary-band
            aria-label="Summary"
            className="flex min-w-0 flex-col gap-3 rounded-lg border p-4"
          >
            <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
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
                        <p className="text-muted-foreground max-w-[40ch] text-xs">
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
              <div className="flex min-w-48 flex-1 basis-56 flex-col gap-1.5">
                {/* The bar is decoration: the line under it says the same in words. */}
                {progress != null && (
                  <div aria-hidden className="bg-muted h-1.5 w-full max-w-sm overflow-hidden rounded-full">
                    <div
                      className="bg-primary h-full rounded-full"
                      style={{ width: `${Math.round(progress * 100)}%` }}
                    />
                  </div>
                )}
                {!insufficient && nextGradeLine(body) && (
                  <p className="text-muted-foreground text-xs">{nextGradeLine(body)}</p>
                )}
                {composition && (
                  <p className="text-muted-foreground text-xs">{composition}</p>
                )}
                <p className="text-muted-foreground text-xs">
                  {remaining} left to fix
                  {marked > 0 && <> · {marked} marked not right</>}
                </p>
              </div>
              {askCount > 0 && (
                <Button
                  className="ml-auto"
                  nativeButton={false}
                  render={<Link href={questionsHref} />}
                >
                  Start the questions ({askCount})
                </Button>
              )}
            </div>

            {noNumbers && (
              <div
                role="note"
                className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40"
              >
                <p className="font-medium">{noNumbers.label}</p>
                <p className="mt-0.5 max-w-[65ch]">
                  {noNumbers.issue} {noNumbers.why}
                </p>
                <p className="mt-0.5 max-w-[65ch]">{noNumbers.how}</p>
                {tabs.number.length > 0 && (
                  <Button
                    size="xs"
                    variant="link"
                    className="mt-1 h-auto px-0"
                    onClick={() => openTab("number")}
                  >
                    Go to Needs a number ({tabs.number.length})
                  </Button>
                )}
              </div>
            )}

            {stale && (
              <FocusHandoff to={checkRef} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
                <p>Your resume changed since this check. Check again to update it.</p>
                {analyzeButton()}
              </FocusHandoff>
            )}
          </section>

          <GateBanner
            gates={gates}
            kind={kind}
            resumeKey={resumeKey}
            onChanged={reanalyzeReport}
            templateId={templateId}
          />

          {!hasAnything && <p className="text-sm">No issues found.</p>}

          <Tabs value={tab} onValueChange={(value) => selectTab(value as HealthTab)} className="gap-4">
            <TabsList aria-label="Health report sections">
              {/* The name says the count in one phrase (SYSTEM.md §12: a count beside a flex item
                  can drop out of the accessible name). */}
              {HEALTH_TABS.map((t) => (
                <TabsTrigger
                  key={t.id}
                  value={t.id}
                  aria-label={`${t.label} ${countOf(t.id)}`}
                  className="gap-1.5 px-2.5"
                >
                  {t.label} <span className="tabular-nums">{countOf(t.id)}</span>
                </TabsTrigger>
              ))}
            </TabsList>
            {CARD_TABS.map((id) => (
              <TabsContent key={id} value={id} keepMounted data-health-tab={id} className="space-y-6">
                {cardTab(id)}
              </TabsContent>
            ))}
            <TabsContent value="shorten" keepMounted data-health-tab="shorten" className="space-y-4">
              {tabs.shorten.length === 0 ? (
                nothingHere
              ) : resumeData == null ? (
                noResumeText
              ) : (
                ruleGroups(tabs.shorten).map((group) => (
                  <div key={group.key} className="space-y-2">
                    <FindingGroupHeader
                      id={`group-shorten-${group.key}`}
                      title={group.title}
                      findings={group.findings}
                      nScoreable={nScoreable}
                    />
                    <ShortenList
                      notes={group.findings}
                      data={resumeData}
                      kind={kind}
                      resumeKey={resumeKey}
                      onApplied={invalidateAfterApply}
                      locked={false}
                      onReanalyze={() => void reanalyzeReport()}
                    />
                  </div>
                ))
              )}
            </TabsContent>
            {/* Kept mounted with every report: it holds the kept Demonstrate-skill drafts, and the
                Wording group's Edit word list is reachable with no wording hits. */}
            <TabsContent value="notes" keepMounted data-health-tab="notes">
              <NotesTable
                notes={tabs.notes}
                data={resumeData}
                kind={kind}
                resumeKey={resumeKey}
                onApplied={invalidateAfterApply}
                locked={false}
                onReanalyze={() => void reanalyzeReport()}
                onWordingChanged={reanalyzeReport}
              />
            </TabsContent>
            <TabsContent value="done" keepMounted data-health-tab="done">
              <DoneTab
                resolved={resolved}
                disputes={disputeRows}
                disputesFailed={isLoadFailure(storedDisputes)}
                onRetryDisputes={() => void storedDisputes.refetch()}
                overrides={overrides}
                data={resumeData}
                onReopen={reopen}
                onBackToAutomatic={(hash) => overrideClassification(hash, null, "")}
              />
            </TabsContent>
          </Tabs>
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
    </PageShell>
  );
}
