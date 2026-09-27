"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useSingleFlight } from "@/hooks/use-single-flight";
import { getDisputes, overrideLevel, reopenDispute, runLintReport } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import {
  checkDoneWords,
  disputeChangedRating,
  disputeTabMove,
  explainScoreDelta,
  groupTitle,
  hasOpenRating,
  mergeResolved,
  resolvedFindings,
  type ActionTab,
} from "@/lib/health-report";
import type {
  DisputeResult,
  EvidenceLevel,
  LintFinding,
  LintReport,
  ResumeData,
} from "@/lib/types";

export type ScoreDelta = {
  fromGrade: string;
  fromScore: number;
  toGrade: string;
  toScore: number;
  explanation: string | null;
};

/**
 * Every run of the health check the report page makes, and what it keeps across them: the score
 * delta, this page session's fixes, the "Not right?" replies (by content hash), the bullets a
 * dispute lifted, and the count of applies since the last check.
 */
export function useHealthRuns({
  kind,
  resumeKey,
  report,
  resumeData,
  onDisputeMovesTab,
}: {
  kind: "base" | "application";
  resumeKey: string;
  /** The report on screen (the report query's data). */
  report: LintReport | undefined;
  resumeData: ResumeData | null;
  /**
   * A dispute's re-run moved its bullet to another tab: the page opens it in the same render the
   * re-run's report (`reportId`) arrives in, so the new card mounts in the open panel.
   */
  onDisputeMovesTab: (tab: ActionTab, reportId: string) => void;
}) {
  const qc = useQueryClient();
  const reportKey = ["resume-lint", kind, resumeKey];
  const [appliedCount, setAppliedCount] = useState(0);
  const [scoreDelta, setScoreDelta] = useState<ScoreDelta | null>(null);
  const [resolved, setResolved] = useState<LintFinding[]>([]);
  const priorFindings = useRef<LintFinding[]>([]);
  const priorScore = useRef<{ grade: string; score: number } | null>(null);

  useEffect(() => {
    if (!report || priorScore.current) return;
    priorFindings.current = report.findings;
    priorScore.current = { grade: report.grade, score: report.score };
  }, [report]);

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
      // "Fixed this session" is the page's session: it grows across re-runs, and a fix whose
      // finding is open again leaves it.
      const fresh = resolvedFindings(priorFindings.current, result.findings);
      setResolved((kept) => mergeResolved(kept, fresh, result.findings));
    }
    priorFindings.current = result.findings;
    priorScore.current = { grade: result.grade, score: result.score };
    qc.setQueryData(reportKey, result);
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
      adoptReport(result, Boolean(report));
      setAppliedCount(0);
      // "Too little to grade" in the band: the toast never names a grade.
      toast.success(checkDoneWords(result));
    },
    onError: (err: Error) => toast.error(couldnt("check the resume", err)),
  });
  // One check per gesture: a double click ran the check twice.
  const analyzeOnce = useSingleFlight(analyze.mutate);

  // The latest "Not right?" reply per bullet (content hash). Kept here, not in the card: a dispute
  // that moves the rating runs the report again, which can replace the card with a new one.
  const [disputes, setDisputes] = useState<Record<string, DisputeResult>>({});
  // The bullet of a dispute whose re-run may replace its card: the card mounting on it opens on the
  // reply. Its landing or collapse clears it, as does any other action (Check again, an override,
  // an Apply).
  const [lastDisputed, setLastDisputed] = useState<string | null>(null);
  // Bullets a dispute's own re-run lifted out of the report: their Fixed entry carries the reply.
  const [lifted, setLifted] = useState<ReadonlySet<string>>(new Set());

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

  // What the user marked not right, for the Done tab and the band's count.
  const disputesKey = ["resume-lint", kind, resumeKey, "disputes"];
  const storedDisputes = useQuery({
    queryKey: disputesKey,
    queryFn: () => getDisputes(kind, resumeKey),
  });

  const afterDispute = async (result: DisputeResult, where: LintFinding["location"]) => {
    const hash = result.content_hash;
    setDisputes((d) => ({ ...d, [hash]: result }));
    // Every dispute is a new Done row, whether or not it moved the rating.
    void qc.invalidateQueries({ queryKey: disputesKey });
    if (!disputeChangedRating(result)) return;
    setLastDisputed(hash);
    const fresh = await runLatest();
    if (!fresh) return;
    // A bullet the re-run moves to another tab ("no number exists": a number question becomes a
    // detail question): open that tab first, so its new card mounts in the open panel on its reply.
    const moved = disputeTabMove(priorFindings.current, fresh.findings, hash, where);
    if (moved) onDisputeMovesTab(moved, fresh.id);
    adoptReport(fresh, true);
    if (!hasOpenRating(fresh.findings, hash)) setLifted((l) => new Set(l).add(hash));
    await qc.invalidateQueries({
      queryKey: ["resume-lint", kind, resumeKey],
    });
  };

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

  return {
    analyze,
    analyzeOnce,
    appliedCount,
    scoreDelta,
    resolved,
    disputes,
    lastDisputed,
    setLastDisputed,
    lifted,
    storedDisputes,
    afterDispute,
    reanalyzeReport,
    overrideClassification,
    reopen,
    invalidateAfterApply,
  };
}
