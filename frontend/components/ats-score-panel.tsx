"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  ApiError,
  apiFetch,
  createApplicationFromBase,
  createTailoringSession,
  listAtsScores,
  listTailoringSessions,
  runAtsScores,
} from "@/lib/api";
import { baseResumeLabel, type AtsScore, type TailoringSession } from "@/lib/types";

const SUBSCORE_LABELS: {
  key: "keyword" | "placement_recency" | "semantic_fit" | "title" | "format";
  label: string;
}[] = [
  { key: "keyword", label: "Keywords" },
  { key: "placement_recency", label: "Placement & recency" },
  { key: "semantic_fit", label: "Semantic fit" },
  { key: "title", label: "Title" },
  { key: "format", label: "Format" },
];

function SubscoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground text-xs">{label}</span>
        <span className="text-xs font-medium tabular-nums">{pct}</span>
      </div>
      <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full transition-[width]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function AtsScoreCard({
  score,
  top,
  index,
  creating,
  onAnalyze,
  analyzeDisabled,
  jobId,
  openSession,
  onAppliedAsIs,
  applyingAsIs,
}: {
  score: AtsScore;
  top: boolean;
  index: number;
  creating: boolean;
  onAnalyze: () => void;
  analyzeDisabled: boolean;
  jobId: string;
  openSession: TailoringSession | null;
  onAppliedAsIs: () => void;
  applyingAsIs: boolean;
}) {
  const gateWarnings = score.subscores_json.gate_warnings ?? [];
  const resolvedCount = openSession?.resolutions_json.length ?? 0;
  return (
    <Card
      className={cn(
        "animate-fade-rise",
        top && "border-primary/50 ring-primary/20 ring-1",
      )}
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <CardTitle className="min-w-0 text-sm leading-tight font-medium">
          {baseResumeLabel(score.target_id)}
        </CardTitle>
        {top && <Badge className="shrink-0">Best match</Badge>}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-2xl font-semibold tabular-nums">
          {score.composite.toFixed(1)}
          <span className="text-muted-foreground text-sm font-normal"> / 100</span>
        </div>
        <div className="space-y-1.5">
          {SUBSCORE_LABELS.map(({ key, label }) => (
            <SubscoreBar
              key={key}
              label={label}
              value={score.subscores_json[key] ?? 0}
            />
          ))}
        </div>
        {gateWarnings.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {gateWarnings.map((warning) => (
              <Badge key={warning} variant="destructive" className="h-auto whitespace-normal">
                {warning}
              </Badge>
            ))}
          </div>
        )}
        {(score.coverage_warning || score.subscores_json?.coverage_warning) && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300">
            <p className="font-medium">
              {score.coverage_warning || score.subscores_json?.coverage_warning}
            </p>
            {(score.jd_skills_extracted_count || score.subscores_json?.jd_skills_extracted_count) ? (
              <p className="mt-0.5 text-[11px] opacity-80">
                Only {score.jd_skills_matched_count ?? score.subscores_json?.jd_skills_matched_count ?? 0} of{" "}
                {score.jd_skills_extracted_count ?? score.subscores_json?.jd_skills_extracted_count ?? 0} JD skills recognized
                ({Math.round(((score.coverage_ratio ?? score.subscores_json?.coverage_ratio ?? 0) * 100))}% coverage).
              </p>
            ) : null}
          </div>
        )}
        {openSession ? (
          <div className="space-y-1.5">
            <Button
              className="w-full"
              size="sm"
              nativeButton={false}
              render={
                <Link href={`/jobs/${jobId}/tailor/${openSession.id}`}>
                  Resume gap analysis
                  {resolvedCount > 0 ? ` (${resolvedCount} resolved)` : ""}
                </Link>
              }
            />
            <Button
              className="w-full"
              size="sm"
              variant="ghost"
              onClick={onAnalyze}
              disabled={analyzeDisabled}
            >
              {creating ? <Loader2 className="animate-spin" /> : null}
              {creating ? "Analyzing gaps…" : "Start over"}
            </Button>
          </div>
        ) : (
          <Button
            className="w-full"
            size="sm"
            onClick={onAnalyze}
            disabled={analyzeDisabled}
          >
            {creating ? <Loader2 className="animate-spin" /> : <Wand2 />}
            {creating ? "Analyzing gaps…" : "Analyze gaps & tailor"}
          </Button>
        )}
        <Button
          className="text-muted-foreground w-full"
          size="sm"
          variant="ghost"
          onClick={onAppliedAsIs}
          disabled={applyingAsIs}
        >
          {applyingAsIs ? <Loader2 className="animate-spin" /> : <Check />}
          Applied with base resume
        </Button>
      </CardContent>
    </Card>
  );
}

/**
 * ATS Scores tab: deterministic per-base composite + subscore breakdown.
 * Auto-runs scoring on first visit (fast — no LLM); "Analyze gaps & tailor"
 * creates a tailoring session (LLM enrichment pass) and navigates to it.
 */
export function AtsScorePanel({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();

  const scores = useQuery({
    queryKey: ["ats-scores", jobId],
    queryFn: () => listAtsScores(jobId),
  });

  // Open tailoring sessions let a card offer "Resume gap analysis". On
  // loading/error this stays empty, so cards fall back to the normal button.
  const sessions = useQuery({
    queryKey: ["tailoring-sessions", jobId],
    queryFn: () => listTailoringSessions(jobId),
  });

  // Newest OPEN session per base resume (created_at desc; ISO strings sort lexically).
  const openSessionByBase = new Map<string, TailoringSession>();
  for (const s of sessions.data ?? []) {
    if (s.status !== "open") continue;
    const existing = openSessionByBase.get(s.base_resume);
    if (!existing || s.created_at > existing.created_at) {
      openSessionByBase.set(s.base_resume, s);
    }
  }

  const run = useMutation({
    mutationFn: () => runAtsScores(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const createSession = useMutation({
    mutationFn: (baseResume: string) => createTailoringSession(jobId, baseResume),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["tailoring-sessions", jobId] });
      if (session.health_warning) {
        toast.warning(session.health_warning, { duration: 8000 });
      }
      router.push(`/jobs/${jobId}/tailor/${session.id}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // "Applied with base resume": the user override for skipping tailoring
  // entirely (applied off-platform with the untouched base). One action:
  // from-base application (reuse policy updates the job's newest app for that
  // base — replaces any tailored draft, version history keeps it) + status
  // applied, which also auto-closes any open proposal on the job server-side.
  const appliedAsIs = useMutation({
    mutationFn: async (baseResume: string) => {
      const app = await createApplicationFromBase(jobId, baseResume);
      await apiFetch(`/api/applications/${app.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "applied" }),
      });
    },
    onSuccess: () => {
      toast.success("Recorded as applied with the base resume");
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["jobs", "without-application"] });
      qc.invalidateQueries({ queryKey: ["job-detail", jobId] });
      qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const appliedAsIsClick = async (baseResume: string) => {
    const ok = await confirm({
      title: "Applied with base resume?",
      description:
        `Records an application using ${baseResumeLabel(baseResume)} as-is and marks it Applied. ` +
        "Any tailored draft for this job and base is replaced by the base content " +
        "(version history keeps every prior draft), and any open agent proposal " +
        "for this job is closed.",
      confirmLabel: "Mark applied",
    });
    if (ok) appliedAsIs.mutate(baseResume);
  };

  // First visit: no persisted scores yet — run the (fast, deterministic) engine once.
  const autoRan = useRef(false);
  const { mutate: runMutate } = run;
  useEffect(() => {
    if (scores.isSuccess && scores.data.length === 0 && !autoRan.current) {
      autoRan.current = true;
      runMutate();
    }
  }, [scores.isSuccess, scores.data, runMutate]);

  const baseRows = (scores.data ?? [])
    .filter((s) => s.phase === "base")
    .sort((a, b) => b.composite - a.composite);

  if (scores.isLoading || (baseRows.length === 0 && run.isPending)) {
    return (
      <div className="@container">
        <div className="grid gap-3 @md:grid-cols-2 @3xl:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (scores.isError) {
    return (
      <LoadErrorState
        title="Couldn't load ATS scores."
        detail={(scores.error as Error)?.message}
        retrying={scores.isFetching}
        onRetry={() => void scores.refetch()}
      />
    );
  }

  if (baseRows.length === 0) {
    // A 422 means the job itself can't be scored (e.g. no extracted skills) —
    // retrying can't succeed, so show the reason instead of a dead-end button.
    const unscorable =
      run.error instanceof ApiError && run.error.status === 422 ? run.error.message : null;
    return (
      <div className="flex flex-col items-center gap-3 py-8">
        <p className="text-muted-foreground text-sm">{unscorable ?? "No ATS scores yet."}</p>
        {!unscorable && (
          <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending && <Loader2 className="animate-spin" />}
            {run.isPending ? "Scoring…" : "Run ATS scoring"}
          </Button>
        )}
      </div>
    );
  }

  const pendingBase = createSession.isPending ? createSession.variables : null;

  return (
    <div className="@container space-y-3">
      <div className="flex items-center justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => run.mutate()}
          disabled={run.isPending}
        >
          <RefreshCw className={run.isPending ? "animate-spin" : undefined} />
          {run.isPending ? "Re-scoring…" : "Re-score base resumes"}
        </Button>
      </div>
      <div className="grid gap-3 @md:grid-cols-2 @3xl:grid-cols-3">
        {baseRows.map((score, i) => (
          <AtsScoreCard
            key={score.id}
            score={score}
            top={i === 0}
            index={i}
            creating={pendingBase === score.target_id}
            analyzeDisabled={createSession.isPending}
            onAnalyze={() => createSession.mutate(score.target_id)}
            jobId={jobId}
            openSession={openSessionByBase.get(score.target_id) ?? null}
            onAppliedAsIs={() => appliedAsIsClick(score.target_id)}
            applyingAsIs={
              appliedAsIs.isPending && appliedAsIs.variables === score.target_id
            }
          />
        ))}
      </div>
    </div>
  );
}
