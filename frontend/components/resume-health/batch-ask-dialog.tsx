"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  emptyMetricAsk,
  MetricAskInput,
  metricContextFromValue,
  type MetricAskValue,
} from "@/components/resume-health/metric-ask-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, answerAsk, apiFetch } from "@/lib/api";
import {
  answerMatchesFinding,
  isContentChangedError,
  STALE_APPLY_HINT,
  type StoredAskAnswer,
} from "@/lib/health-report";
import { toastRewriteError } from "./report-errors";
import { wordDiff } from "@/lib/word-diff";
import { textAtLocation } from "@/components/resume-health/finding-cards";
import type { LintFinding, ResumeData } from "@/lib/types";

type RowState = {
  finding: LintFinding;
  metric: MetricAskValue;
  suggestion: string | null;
  error: "422" | "409" | null;
  pending: boolean;
};

const POOL = 3;

async function mapPool<T>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next;
      next += 1;
      await fn(items[index], index);
    }
  }
  const n = Math.min(limit, items.length);
  await Promise.all(Array.from({ length: n }, () => worker()));
}

export function BatchAskDialog({
  open,
  onOpenChange,
  findings,
  data,
  kind,
  resumeKey,
  locked,
  storedAnswers,
  onApplied,
  onReanalyze,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  findings: LintFinding[];
  data: ResumeData;
  kind: "base" | "application";
  resumeKey: string;
  locked?: boolean;
  storedAnswers?: Record<string, StoredAskAnswer>;
  onApplied: () => void;
  onReanalyze?: () => void;
}) {
  const initial = useMemo<RowState[]>(
    () =>
      findings.map((finding) => {
        const stored = storedAnswers?.[finding.id];
        const fresh = answerMatchesFinding(stored, finding.content_hash);
        return {
          finding,
          metric: fresh
            ? {
                ...emptyMetricAsk(),
                somethingElse: true,
                freeText: stored.answer,
              }
            : emptyMetricAsk(),
          suggestion: fresh ? (stored.suggestion ?? null) : null,
          error: null,
          pending: false,
        };
      }),
    [findings, storedAnswers],
  );
  const [rows, setRows] = useState<RowState[]>(initial);
  const [drafting, setDrafting] = useState(false);
  const [applying, setApplying] = useState(false);

  const patch = (index: number, next: Partial<RowState>) => {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...next } : row)),
    );
  };

  const readyCount = rows.filter(
    (row) => metricContextFromValue(row.metric).length > 0,
  ).length;
  const drafted = rows.filter((row) => row.suggestion);
  const reviewReady = drafted.length > 0;

  const draftAll = async () => {
    setDrafting(true);
    try {
      await mapPool(rows, POOL, async (row, index) => {
        const context = metricContextFromValue(row.metric);
        if (!context) return;
        patch(index, { pending: true, error: null });
        try {
          const result = await answerAsk(kind, resumeKey, row.finding.id, context);
          patch(index, {
            suggestion: result.suggestion,
            pending: false,
            error: null,
          });
        } catch (err) {
          const apiErr = err as ApiError;
          if (apiErr instanceof ApiError && apiErr.status === 422) {
            patch(index, { pending: false, error: "422", suggestion: null });
            return;
          }
          if (apiErr instanceof ApiError && isContentChangedError(apiErr)) {
            patch(index, { pending: false, error: "409", suggestion: null });
            return;
          }
          patch(index, { pending: false });
          toast.error(err instanceof Error ? err.message : String(err));
        }
      });
    } finally {
      setDrafting(false);
    }
  };

  const applyOne = async (row: RowState) => {
    const currentText = textAtLocation(data, row.finding);
    if (!row.suggestion || currentText == null) return;
    const { section, index, bullet_index } = row.finding.location;
    const hash =
      row.finding.content_hash != null
        ? { expected_content_hash: row.finding.content_hash }
        : {};
    const op =
      section === "summary"
        ? { kind: "replace_summary", value: row.suggestion, ...hash }
        : {
            kind: "replace_bullet",
            section,
            index,
            bullet_index,
            value: row.suggestion,
            ...hash,
          };
    const path =
      kind === "base"
        ? `/api/base-resumes/${resumeKey}/edits`
        : `/api/applications/${resumeKey}/edits`;
    await apiFetch(path, {
      method: "PATCH",
      body: JSON.stringify({ ops: [op] }),
    });
  };

  const applyAll = async () => {
    setApplying(true);
    try {
      for (const row of drafted) {
        try {
          await applyOne(row);
          onApplied();
        } catch (err) {
          toastRewriteError(err, onReanalyze);
          return;
        }
      }
      toast.success("Applied and saved as a new version");
      onOpenChange(false);
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[min(96vw,48rem)] max-w-[min(96vw,48rem)] flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            Answer the number questions ({findings.length})
          </DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {rows.map((row, index) => {
            const quote = textAtLocation(data, row.finding);
            return (
              <div
                key={row.finding.id}
                className="grid gap-3 border-b py-2 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
              >
                <blockquote className="text-muted-foreground truncate text-sm italic">
                  {quote ?? row.finding.issue}
                </blockquote>
                <div className="min-w-0 space-y-2">
                  {row.suggestion && quote ? (
                    <p className="text-sm leading-relaxed">
                      {wordDiff(quote, row.suggestion).map((token, i) => (
                        <span
                          key={i}
                          className={
                            token.kind === "removed"
                              ? "bg-red-500/10 text-red-600 line-through dark:text-red-400"
                              : token.kind === "added"
                                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                                : undefined
                          }
                        >
                          {token.text}{" "}
                        </span>
                      ))}
                    </p>
                  ) : row.error === "422" ? (
                    <p className="text-muted-foreground text-xs">
                      Couldn&apos;t safely rewrite
                    </p>
                  ) : row.error === "409" ? (
                    <p className="text-amber-700 dark:text-amber-400 text-xs">
                      Stale — re-analyze
                    </p>
                  ) : (
                    <MetricAskInput
                      value={row.metric}
                      onChange={(metric) => patch(index, { metric })}
                      disabled={locked || drafting}
                    />
                  )}
                  {row.suggestion && (
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={locked || applying}
                      title={locked ? STALE_APPLY_HINT : undefined}
                      onClick={async () => {
                        try {
                          await applyOne(row);
                          toast.success("Applied and saved as a new version");
                          onApplied();
                          patch(index, { suggestion: null });
                        } catch (err) {
                          toastRewriteError(err, onReanalyze);
                        }
                      }}
                    >
                      Apply
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <DialogFooter>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {reviewReady ? (
            <Button
              size="sm"
              disabled={locked || applying || drafted.length === 0}
              onClick={() => void applyAll()}
            >
              {applying ? "Applying…" : `Apply all (${drafted.length})`}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={locked || drafting || readyCount === 0}
              onClick={() => void draftAll()}
            >
              {drafting ? "Drafting…" : `Draft ${readyCount} rewrite${readyCount === 1 ? "" : "s"}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
