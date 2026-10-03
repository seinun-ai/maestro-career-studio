"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

import { GuardedLink as Link } from "@/components/guarded-link";
import { IconButton } from "@/components/icon-button";
import { LoadErrorState } from "@/components/load-error-state";
import { PageHeader, PageShell } from "@/components/page-shell";
import { AcceptAllDialog } from "@/components/resume-health/accept-all-dialog";
import { DisputeBox } from "@/components/resume-health/dispute-box";
import { DiffText, SourceQuote, SuggestionCopyOnly } from "@/components/resume-health/judged-text";
import { MetricAskInput } from "@/components/resume-health/metric-ask-input";
import {
  canSave,
  copyOnly,
  fetchBase,
  initialRow,
  isAnswered,
  rowContext,
  rowText,
  type PassRow,
} from "@/components/resume-health/pass-rows";
import { usePassWrites } from "@/components/resume-health/use-pass-writes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { focusIfDropped, useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useLoadFailureError } from "@/hooks/use-last-seen";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { ApiError, answerAsk, getAskAnswers, getLintReport, runLintReport } from "@/lib/api";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { focusTarget } from "@/lib/focus";
import {
  bulletContext,
  isContentChangedError,
  isMetricAsk,
  mapPool,
  parseHealthTab,
  passOutcome,
  passOutcomeWords,
  passProgress,
  passRowDisputable,
  passRowOpen,
  reportIsStale,
  staleFindingIds,
  writeWordingsLabel,
  type BulletContext,
} from "@/lib/health-report";
import { isLoadFailure } from "@/lib/query-state";
import { cn } from "@/lib/utils";
import type { DisputeResult, LintReport } from "@/lib/types";

/** Drafts written at once: each is a model call. */
const POOL = 3;

/**
 * The question pass: every ask in the health report on one page, answered in one go or row by row.
 * Rows draft three at a time through the same `answerAsk` as the report's cards; accepted rows go
 * to the resume as ONE hash-guarded write, undone only while that write is still the latest version.
 * Leaving re-runs the check in the background and says what the pass did in one toast.
 */
export function QuestionPass({ resumeKey }: { resumeKey: string }) {
  // The web report is base resumes only (as HealthReportPage).
  const kind = "base" as const;
  const qc = useQueryClient();
  // Back returns to the report's tab the user came from (`?from=`, written by Start the questions).
  // Read with useSearchParams; the page keeps `use(searchParams)` (SYSTEM.md §12).
  const from = parseHealthTab(useSearchParams().get("from"));
  const reportHref = `/base-resumes/${resumeKey}/health${from ? `?tab=${from}` : ""}`;

  const baseQuery = useQuery({ queryKey: ["base-resumes", resumeKey], queryFn: () => fetchBase(resumeKey) });
  const report = useQuery<LintReport>({
    queryKey: ["resume-lint", kind, resumeKey],
    queryFn: () => getLintReport(kind, resumeKey),
    retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });
  const answers = useQuery({
    queryKey: ["resume-lint", kind, resumeKey, "answers"],
    queryFn: () => getAskAnswers(kind, resumeKey),
  });
  const reportError = useLoadFailureError(report);
  const noReportYet = reportError instanceof ApiError && reportError.status === 404;

  // The rows, and the report they came from, are fixed when the pass opens: a re-run elsewhere
  // never reorders what the user is answering.
  const [start, setStart] = useState<LintReport | null>(null);
  const [rows, setRows] = useState<PassRow[] | null>(null);
  const answersSettled = answers.isSuccess || answers.isError;
  if (rows == null && report.data && baseQuery.data && answersSettled) {
    const data = baseQuery.data.data;
    setStart(report.data);
    setRows(
      report.data.findings
        .filter((f) => f.type === "ask")
        .map((f) => initialRow(f, data, answers.data?.[f.id])),
    );
  }
  const liveData = baseQuery.data?.data ?? null;

  const patch = (key: string, next: Partial<PassRow>) =>
    setRows((current) => current && current.map((row) => (row.key === key ? { ...row, ...next } : row)));

  // A stale report: the rows whose own bullet drifted since the check open as changed.
  useEffect(() => {
    if (!start || !reportIsStale(start) || !liveData) return;
    let cancelled = false;
    void staleFindingIds(start.findings, liveData).then((ids) => {
      if (cancelled || ids.size === 0) return;
      setRows(
        (current) =>
          current &&
          current.map((row) =>
            ids.has(row.finding.id) && (row.status === "answering" || row.status === "drafted")
              ? { ...row, status: "changed" }
              : row,
          ),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [start, liveData]);

  // "Not right?" replies, by content hash. Kept here, not on the report page: the pass never re-runs
  // the check under the user, so a reply stays on its row; leaving re-runs it (closePass).
  const [disputes, setDisputes] = useState<Record<string, DisputeResult>>({});
  const afterDispute = (row: PassRow) => async (result: DisputeResult) => {
    setDisputes((current) => ({ ...current, [result.content_hash]: result }));
    // New wording the note brought goes to the row's review, where Accept applies it.
    if (result.suggestion != null) patch(row.key, { status: "drafted", suggestion: result.suggestion, edited: null });
  };

  // --- Drafting ------------------------------------------------------------------------------
  const refreshAnswers = () => void qc.invalidateQueries({ queryKey: ["resume-lint", kind, resumeKey, "answers"] });
  /** One row's draft; a failure other than the row's own (changed, nothing to rewrite) is returned. */
  const draftRow = async (row: PassRow): Promise<unknown> => {
    patch(row.key, { status: "drafting" });
    try {
      const result = await answerAsk(kind, resumeKey, row.finding.id, rowContext(row));
      patch(row.key, { status: "drafted", suggestion: result.suggestion, edited: null });
      return null;
    } catch (err) {
      if (err instanceof ApiError && isContentChangedError(err)) patch(row.key, { status: "changed" });
      else if (err instanceof ApiError && err.status === 422) patch(row.key, { status: "unrewritable" });
      else {
        patch(row.key, { status: "failed" });
        return err;
      }
      return null;
    }
  };
  const writeAll = useMutation({
    // The answers are read on the click: every row it drafts is queued, which shuts its fields, Skip
    // and Not right? until its draft lands (`passRowOpen`).
    onMutate: (targets: PassRow[]) => {
      const keys = new Set(targets.map((row) => row.key));
      setRows((current) => current && current.map((row) => (keys.has(row.key) ? { ...row, status: "queued" } : row)));
    },
    // Rows fill in as each draft finishes, three at a time.
    mutationFn: async (targets: PassRow[]) => {
      let firstError: unknown = null;
      await mapPool(targets, POOL, async (row) => {
        const err = await draftRow(row);
        if (err && !firstError) firstError = err;
      });
      return firstError;
    },
    onSuccess: (err) => {
      refreshAnswers();
      // One toast for the batch; each failed row says so on itself.
      if (err) toast.error(couldnt("write new wording", err));
    },
  });
  // One batch per gesture: a double click drafted every row twice.
  const writeOnce = useSingleFlight(writeAll.mutate);
  const retrying = useRef(new Set<string>());
  const tryAgain = async (row: PassRow) => {
    if (retrying.current.has(row.key)) return;
    retrying.current.add(row.key);
    try {
      const err = await draftRow(row);
      refreshAnswers();
      if (err) toast.error(couldnt("write new wording", err));
    } finally {
      retrying.current.delete(row.key);
    }
  };

  // --- Saving, Undo and Write it again ------------------------------------------------------------
  const { saveOnce, saving, recheck } = usePassWrites({ kind, resumeKey, setRows });

  // --- Closing: the check runs again in the background, and one toast says what the pass did -----
  const closePass = (before: LintReport, passRows: PassRow[], disputed: Record<string, DisputeResult>) => {
    const skipped = passRows.filter((row) => row.skipped).length;
    const hashes = new Set(Object.keys(disputed));
    if (!passRows.some((row) => row.status === "saved") && hashes.size === 0 && skipped === 0) return;
    const reportKey = ["resume-lint", kind, resumeKey];
    void runLintReport(kind, resumeKey).then(
      async (after) => {
        // The report page may be showing by now: an older fetch must not land over this report.
        await qc.cancelQueries({ queryKey: reportKey, exact: true });
        // Not over a newer one either (a Check again on the report page that finished first).
        const cached = qc.getQueryData<LintReport>(reportKey);
        if (!cached || Date.parse(cached.created_at) <= Date.parse(after.created_at)) {
          qc.setQueryData(reportKey, after);
        }
        void qc.invalidateQueries({ queryKey: reportKey });
        const ids = new Set(passRows.map((row) => row.key));
        toast.success(passOutcomeWords(passOutcome(before, after, ids, hashes, skipped)));
      },
      (err: unknown) => toast.error(couldnt("check the resume", err)),
    );
  };
  const closing = useRef<(() => void) | null>(null);
  useEffect(() => {
    closing.current = start && rows ? () => closePass(start, rows, disputes) : null;
  });
  useEffect(() => () => closing.current?.(), []);

  // --- What the page shows --------------------------------------------------------------------
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const all = rows ?? [];
  const writable = all.filter((row) => !row.skipped && passRowOpen(row.status) && rowContext(row).length > 0);
  // Only wording that changes its bullet: a batch that changes nothing writes no version to undo.
  const acceptable = all.filter((row) => !row.skipped && canSave(row));
  const checking = all.some((row) => row.status === "checking");
  // The page's ONE filled button: Write while anything is left to write, then Accept all shown.
  const primary = writable.length > 0 || acceptable.length === 0 ? "write" : "accept";
  const progress = passProgress(all.map((row) => ({ answered: isAnswered(row, disputes), skipped: row.skipped })));
  // Typed answers not yet written, and edits not yet saved, live only on this page.
  const unsaved = all.some(
    (row) =>
      (["answering", "failed", "changed", "checking"].includes(row.status) && rowContext(row).length > 0) ||
      (row.status === "drafted" && row.edited != null && row.edited !== row.suggestion),
  );
  useLeaveGuard(unsaved);

  const active = all.find((row) => row.key === activeKey) ?? all[0] ?? null;
  const activeContext = active && liveData ? bulletContext(liveData, active.finding.location) : null;

  const header = (
    <PageHeader
      leading={
        <IconButton
          label="Back to the health report"
          icon={<ArrowLeft className="size-4" />}
          size="icon-sm"
          className="mt-1.5 shrink-0"
          nativeButton={false}
          render={<Link href={reportHref} className="text-muted-foreground" />}
        />
      }
      title="Questions"
      subtitle={baseQuery.data ? (baseQuery.data.display_name ?? baseQuery.data.slug) : undefined}
    />
  );

  if (isLoadFailure(baseQuery)) {
    return (
      <PageShell>
        {header}
        <LoadErrorState
          title="Couldn't load this resume."
          detail={loadErrorDetail(baseQuery.error, "resume")}
          retrying={baseQuery.isFetching}
          onRetry={() => void baseQuery.refetch()}
        />
      </PageShell>
    );
  }
  if (reportError != null && !noReportYet) {
    return (
      <PageShell>
        {header}
        <LoadErrorState
          title="Couldn't load this health report."
          detail={loadErrorDetail(reportError)}
          retrying={report.isFetching}
          onRetry={() => void report.refetch()}
        />
      </PageShell>
    );
  }
  if (noReportYet || (rows != null && rows.length === 0)) {
    return (
      <PageShell>
        {header}
        <div className="flex flex-col items-start gap-3">
          <p className="text-muted-foreground max-w-[65ch] text-sm">
            {noReportYet
              ? "No health report yet. Check your resume first, then answer its questions here."
              : "No questions to answer. Every bullet the check read has what it asks for."}
          </p>
          <Button variant="outline" nativeButton={false} render={<Link href={reportHref} />}>
            Back to the health report
          </Button>
        </div>
      </PageShell>
    );
  }
  if (rows == null || liveData == null) {
    return (
      <PageShell>
        {header}
        <Skeleton className="h-96 w-full max-w-[65ch]" />
      </PageShell>
    );
  }

  return (
    <PageShell>
      {header}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,65ch)_minmax(0,1fr)]">
        <div className="flex min-w-0 max-w-[65ch] flex-col gap-4">
          <p className="text-muted-foreground text-sm">
            Answer what you can, then write the new wordings together. Blank rows wait for next time.
          </p>
          <ol aria-label="Questions" className="flex flex-col gap-4">
            {rows.map((row) => (
              <PassRowView
                key={row.key}
                row={row}
                context={bulletContext(liveData, row.finding.location)}
                kind={kind}
                resumeKey={resumeKey}
                dispute={row.finding.content_hash ? disputes[row.finding.content_hash] : undefined}
                saving={saving}
                recheckBusy={checking}
                onFocus={() => setActiveKey(row.key)}
                onChange={(next) => patch(row.key, next)}
                onAccept={() => saveOnce([row])}
                onTryAgain={() => void tryAgain(row)}
                onRecheck={() => void recheck(row)}
                onDisputed={afterDispute(row)}
              />
            ))}
          </ol>
          <div className="bg-background/95 sticky bottom-4 z-20 flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm shadow-sm">
            <p aria-live="polite">{progress.words}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant={primary === "accept" ? "default" : "tonal"}
                disabled={acceptable.length === 0 || saving}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => setPreviewOpen(true)}
              >
                Accept all shown ({acceptable.length})
              </Button>
              <Button
                size="sm"
                variant={primary === "write" ? "default" : "tonal"}
                disabled={writable.length === 0 || writeAll.isPending}
                // Disables itself while writing: a native `disabled` drops focus.
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={() => writeOnce(writable)}
              >
                {writeAll.isPending ? "Writing…" : writeWordingsLabel(writable.length)}
              </Button>
            </div>
          </div>
        </div>

        {/* At 1280 and up: where the active row's bullet sits, the rest of its item around it. */}
        <aside aria-label="In your resume" className="hidden xl:block">
          {activeContext && <ContextPane context={activeContext} />}
        </aside>
      </div>

      <AcceptAllDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        acceptable={acceptable}
        onAccept={(chosen) => saveOnce(chosen)}
      />
    </PageShell>
  );
}

function ContextPane({ context }: { context: BulletContext }) {
  return (
    <div className="sticky top-6 space-y-2 rounded-lg border p-4">
      <p className="text-sm font-medium">{context.heading}</p>
      {context.dates && <p className="text-muted-foreground text-xs">{context.dates}</p>}
      <ul className="space-y-1">
        {context.bullets.map((bullet, i) => (
          <li
            key={i}
            aria-current={i === context.active ? "true" : undefined}
            className={cn(
              "text-foreground border-l-2 border-transparent py-1 pl-3 text-sm",
              i === context.active && "bg-primary/10 border-l-2 border-primary",
            )}
          >
            {bullet}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PassRowView({
  row,
  context,
  kind,
  resumeKey,
  dispute,
  saving,
  recheckBusy,
  onFocus,
  onChange,
  onAccept,
  onTryAgain,
  onRecheck,
  onDisputed,
}: {
  row: PassRow;
  context: BulletContext | null;
  kind: "base" | "application";
  resumeKey: string;
  dispute?: DisputeResult;
  /** A write is running: Accept waits for it. */
  saving: boolean;
  /** Another row's Write it again is checking: one check at a time. */
  recheckBusy: boolean;
  onFocus: () => void;
  onChange: (next: Partial<PassRow>) => void;
  onAccept: () => void;
  onTryAgain: () => void;
  onRecheck: () => void;
  onDisputed: (result: DisputeResult) => Promise<void>;
}) {
  const rowRef = useRef<HTMLLIElement>(null);
  const answerItRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLTextAreaElement>(null);
  // What replaces the controls that just left (Accept, Write it again): focus lands here.
  const landRef = useRef<HTMLElement | null>(null);
  const setLand = (el: HTMLElement | null) => {
    landRef.current = el;
  };
  const focusNext = useFocusOnNextCommit();
  const shown = useRef(row.status);
  useEffect(() => {
    if (shown.current === row.status) return;
    shown.current = row.status;
    const row_ = rowRef.current;
    focusIfDropped(landRef.current ?? (row_ ? focusTarget(row_) : null));
  }, [row.status]);

  const metricAsk = isMetricAsk(row.finding);
  const answering = ["answering", "queued", "drafting", "failed"].includes(row.status);
  // Queued, drafting and later rows keep their answer as it was read: fields and Skip shut.
  const open = passRowOpen(row.status);
  const text = rowText(row);
  const neighbours = context
    ? { before: context.bullets[context.active - 1] ?? null, after: context.bullets[context.active + 1] ?? null }
    : null;

  if (row.skipped) {
    return (
      <li ref={rowRef} data-pass-row={row.key} onFocus={onFocus} className="rounded-md border px-3 py-2">
        <p className="text-muted-foreground text-xs">{row.finding.label}</p>
        <p className="text-foreground mt-1 line-clamp-2 max-w-[65ch] text-sm">{row.original ?? row.finding.issue}</p>
        <div className="mt-1 flex items-center gap-2">
          <p className="text-muted-foreground text-xs">Skipped for now.</p>
          <Button
            ref={answerItRef}
            size="xs"
            variant="ghost"
            onClick={() => {
              onChange({ skipped: false });
              focusNext(rowRef);
            }}
          >
            Answer it
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li
      ref={rowRef}
      data-pass-row={row.key}
      onFocus={onFocus}
      className="flex flex-col gap-2 rounded-md border px-3 py-3"
    >
      {/* The label names the item. Below 1280 there is no context pane: its dates and the bullets
          around this one sit here. */}
      <p className="text-muted-foreground text-xs">
        {row.finding.label}
        {context?.dates && <span className="xl:hidden"> · {context.dates}</span>}
      </p>
      {neighbours?.before && (
        <p className="text-muted-foreground line-clamp-1 text-xs xl:hidden">Above: {neighbours.before}</p>
      )}
      {row.original != null ? (
        <SourceQuote text={row.original} />
      ) : (
        <p className="text-foreground max-w-[65ch] text-sm">{row.finding.issue}</p>
      )}
      {neighbours?.after && (
        <p className="text-muted-foreground line-clamp-1 text-xs xl:hidden">Below: {neighbours.after}</p>
      )}
      {row.finding.question && (
        <p className="text-foreground max-w-[65ch] text-sm font-medium">
          {row.useAlternative ? row.finding.alt_question : row.finding.question}
        </p>
      )}

      {answering && (
        <div className="space-y-2">
          {metricAsk && row.finding.alt_question && (
            <button
              type="button"
              className="text-primary text-sm underline-offset-2 hover:underline disabled:pointer-events-none disabled:opacity-50"
              aria-expanded={row.useAlternative}
              disabled={!open}
              onClick={() => onChange({ useAlternative: !row.useAlternative })}
            >
              {row.useAlternative ? "Use the number fields" : "No number? Answer this instead"}
            </button>
          )}
          {metricAsk && !row.useAlternative ? (
            <MetricAskInput
              label={row.finding.measure_target ? `Number for: ${row.finding.measure_target}` : undefined}
              value={row.metric}
              onChange={(metric) => onChange({ metric })}
              disabled={!open}
            />
          ) : (
            <Textarea
              rows={2}
              aria-label="Your answer"
              value={row.answer}
              onChange={(e) => onChange({ answer: e.target.value })}
              disabled={!open}
              className="max-w-[65ch] text-sm"
            />
          )}
          {row.status === "queued" && <p className="text-muted-foreground text-xs">Waiting to write…</p>}
          {row.status === "drafting" && <p className="text-muted-foreground text-xs">Writing…</p>}
          {row.status === "failed" && (
            <p className="text-destructive text-xs">Couldn&apos;t write new wording for this one. Try again.</p>
          )}
        </div>
      )}

      {(row.status === "drafted" || row.status === "saving") && row.suggestion != null && (
        <div className="space-y-2 border-t pt-2">
          {copyOnly(row) || row.original == null ? (
            row.original == null ? (
              <p className="text-foreground max-w-[65ch] text-sm">{row.suggestion}</p>
            ) : (
              <SuggestionCopyOnly currentText={row.original} suggestion={row.suggestion} />
            )
          ) : (
            <>
              <div className="bg-surface-container-low rounded-md p-2">
                <DiffText oldText={row.original} newText={text || row.suggestion} />
              </div>
              {row.edited != null && (
                <Textarea
                  ref={editRef}
                  rows={3}
                  aria-label="New wording"
                  value={row.edited}
                  onChange={(e) => onChange({ edited: e.target.value })}
                  className="max-w-[65ch] text-sm"
                />
              )}
            </>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {!copyOnly(row) && row.original != null && (canSave(row) || row.status === "saving") && (
              <Button
                ref={setLand}
                data-accept
                size="sm"
                variant="tonal"
                disabled={saving}
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
                onClick={onAccept}
              >
                {row.status === "saving" ? "Saving…" : "Accept"}
              </Button>
            )}
            {!copyOnly(row) && row.original != null && row.status === "drafted" && !canSave(row) && (
              // The wording is the bullet as it stands: saving it would write no version.
              <p className="text-muted-foreground text-xs">No change to save</p>
            )}
            {!copyOnly(row) && row.original != null && row.edited == null && (
              <Button
                size="sm"
                variant="ghost"
                disabled={row.status === "saving"}
                onClick={() => {
                  onChange({ edited: text });
                  focusNext(editRef);
                }}
              >
                Edit
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              disabled={rowContext(row).length === 0 || row.status === "saving"}
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              onClick={onTryAgain}
            >
              Try again
            </Button>
          </div>
        </div>
      )}

      {row.status === "saved" && (
        <div className="space-y-1 border-t pt-2">
          <DiffText oldText={row.original ?? ""} newText={text} />
          <p
            ref={setLand}
            data-saved
            tabIndex={-1}
            className="text-muted-foreground text-xs outline-none"
          >
            Saved
          </p>
        </div>
      )}

      {(row.status === "changed" || row.status === "checking") && (
        <p
          ref={setLand}
          tabIndex={-1}
          className="text-warning text-xs outline-none"
        >
          This bullet changed.{" "}
          <button
            type="button"
            className="underline underline-offset-2 disabled:opacity-50"
            // One check at a time: another row's Write it again waits for it.
            disabled={row.status === "checking" || recheckBusy}
            onClick={onRecheck}
          >
            {row.status === "checking" ? "Checking…" : "Write it again?"}
          </button>
        </p>
      )}
      {row.status === "gone" && (
        <p
          ref={setLand}
          tabIndex={-1}
          className="text-muted-foreground text-xs outline-none"
        >
          The check has no question for this bullet now.
        </p>
      )}
      {row.status === "unrewritable" && (
        <p
          ref={setLand}
          tabIndex={-1}
          className="text-muted-foreground max-w-[65ch] text-xs outline-none"
        >
          Couldn&apos;t rewrite this one. Edit it yourself.
        </p>
      )}

      <DisputeBox
        finding={row.finding}
        kind={kind}
        resumeKey={resumeKey}
        result={dispute}
        onDisputed={onDisputed}
        // Not while the row is written, saved or changed (`passRowDisputable`).
        locked={!passRowDisputable(row.status)}
        // Its new wording, if any, is in the row's review above (Accept applies it there).
        renderSuggestion={() => null}
        controls={
          row.status !== "saved" && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground"
              disabled={!open && row.status !== "drafted" && row.status !== "unrewritable"}
              onClick={() => {
                onChange({ skipped: true });
                focusNext(answerItRef);
              }}
            >
              Skip for now
            </Button>
          )
        }
      />
    </li>
  );
}
