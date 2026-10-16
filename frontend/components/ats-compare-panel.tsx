"use client";

import { useIsMutating, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MoveRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getAtsCompare, runAtsScoreTarget } from "@/lib/api";
import { DeltaChip } from "@/components/visual";
import { SUBSCORE_LABELS, fixHintLabel, placementLabel, subscoreMoves } from "@/lib/ats-words";
import { CONCEPT_ICONS } from "@/lib/concept-icons";
import { couldnt } from "@/lib/error-text";
import { cn } from "@/lib/utils";
import { formatDelta } from "@/lib/visual";
import type { Application, AtsSkillRow } from "@/lib/types";

/** Signed subscore delta (0–1 float): a ±points label and a bar growing from a centre line, right for a gain, left for a loss. Zero is neutral: no bar. */
function DeltaBar({ label, value }: { label: string; value: number }) {
  const pts = value * 100;
  const { text, sign } = formatDelta(pts);
  const Icon = CONCEPT_ICONS[sign === "up" ? "increase" : sign === "down" ? "decrease" : "none"];
  const tone = sign === "up" ? "text-success" : sign === "down" ? "text-destructive" : "text-muted-foreground";
  const width = Math.min(Math.abs(pts) / 2, 50);
  return (
    <div className="space-y-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground text-body-small">{label}</span>
        <span className={cn("inline-flex items-center gap-1 text-label-medium tabular-nums", tone)}>
          <Icon aria-hidden="true" className="size-3 shrink-0 self-center" />
          {text}
        </span>
      </div>
      <div className="bg-muted relative h-1.5 w-full overflow-hidden rounded-full">
        <div className="bg-border absolute inset-y-0 left-1/2 w-px" />
        {sign === "flat" ? null : (
          <div
            className={cn("absolute inset-y-0", sign === "up" ? "bg-success left-1/2" : "bg-destructive right-1/2")}
            style={{ width: `${width}%` }}
          />
        )}
      </div>
    </div>
  );
}

type Change = "gained" | "lost" | "same";

const CHANGE = {
  gained: { Icon: CONCEPT_ICONS.increase, word: "Gained", tone: "text-success" },
  lost: { Icon: CONCEPT_ICONS.decrease, word: "Lost", tone: "text-destructive" },
  same: { Icon: CONCEPT_ICONS.none, word: "Same", tone: "text-muted-foreground" },
} as const;

const CHANGE_ORDER: Record<Change, number> = { gained: 0, lost: 1, same: 2 };

/** Missing before and matched after is a gain; the reverse a loss; anything else the same. */
function changeOf(before: AtsSkillRow | null, after: AtsSkillRow | null): Change {
  const was = !!before?.matched;
  const is = !!after?.matched;
  return !was && is ? "gained" : was && !is ? "lost" : "same";
}

function ChangeCell({ change }: { change: Change }) {
  const { Icon, word, tone } = CHANGE[change];
  return (
    <span className={cn("inline-flex items-center gap-1.5", tone)}>
      <Icon aria-hidden="true" className="size-4 shrink-0" />
      {word}
    </span>
  );
}

/** The after state's note: where a matched skill sits, or what would fix a missing one. */
function SkillNowCell({ row }: { row: AtsSkillRow | null }) {
  if (!row) return <span className="text-muted-foreground">—</span>;
  const note = row.matched ? placementLabel(row.placement) : fixHintLabel(row.fix_hint);
  return <span className="text-muted-foreground text-body-small">{note ?? (row.matched ? "Matched" : "Missing")}</span>;
}

/** The tailored score's re-score, as one mutation key: the full panel's Update score and step 3's re-score after a
 *  revert share one pending state through it (`useIsMutating`). */
export const tailoredRescoreKey = (applicationId: string) => ["ats-rescore", applicationId] as const;

/**
 * Before-and-after ATS score for a tailored application: the headline score,
 * subscore delta bars, and the per-skill diff. A 422 from the compare
 * endpoint (engine/config version drift between the stored base and tailored
 * rows) is recoverable by scoring both again. `compact` is step 3's strip: one
 * line, `{before} → {after} {+delta}` and the subscores that moved as text.
 * `bare` is the full panel without its card frame, for step 3's Score
 * breakdown disclosure.
 */
export function AtsComparePanel({
  app,
  jobId,
  readOnly = false,
  compact = false,
  bare = false,
}: {
  app: Application;
  jobId: string;
  readOnly?: boolean;
  compact?: boolean;
  bare?: boolean;
}) {
  const qc = useQueryClient();
  // Any re-score of this tailored resume, from here or from step 3's revert.
  const rescoring = useIsMutating({ mutationKey: tailoredRescoreKey(app.id) }) > 0;

  const compare = useQuery({
    queryKey: ["ats-compare", app.id],
    queryFn: () => getAtsCompare(app.id),
    // 422s are deterministic (version mismatch / missing tailored resume) —
    // retrying only delays the actionable error state.
    retry: (failureCount, err) =>
      !(err instanceof ApiError && err.status === 422) && failureCount < 2,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["ats-compare", app.id] });
    qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });
  };

  const rescoreBoth = useMutation({
    mutationFn: async () => {
      await runAtsScoreTarget(jobId, "base_resume", app.base_resume, "base");
      await runAtsScoreTarget(jobId, "application", app.id, "tailored");
    },
    onSuccess: () => {
      toast.success("Match scores updated");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("update the scores", err)),
  });

  const rescoreTailored = useMutation({
    mutationKey: tailoredRescoreKey(app.id),
    mutationFn: () => runAtsScoreTarget(jobId, "application", app.id, "tailored"),
    onSuccess: () => {
      toast.success("Match score updated");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("update the score", err)),
  });

  if (compact) {
    if (compare.isLoading) return <Skeleton className="animate-shimmer h-6 w-64" />;
    if (compare.isError || !compare.data) {
      const recoverable = compare.error instanceof ApiError && compare.error.status === 422;
      return (
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-muted-foreground text-body-small">{couldnt("compare the scores", compare.error)}</span>
          {recoverable ? (
            <Button
              variant="outline"
              size="sm"
              pending={rescoreBoth.isPending}
              disabled={readOnly}
              onClick={() => rescoreBoth.mutate()}
            >
              <RefreshCw />
              {rescoreBoth.isPending ? "Updating…" : "Update both scores"}
            </Button>
          ) : null}
        </div>
      );
    }
    const { base, tailored, delta } = compare.data;
    const moved = subscoreMoves(delta.subscores, formatDelta);
    return (
      // Dims while the tailored score is being scored again: the numbers are about to change.
      <div
        className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"
        data-pending={rescoring ? "true" : undefined}
        aria-busy={rescoring || undefined}
      >
        <span className="inline-flex items-center gap-1.5 text-title-medium tabular-nums">
          <span className="sr-only">Match score before and after: </span>
          <span className="text-muted-foreground">{base.composite.toFixed(1)}</span>
          <MoveRight aria-hidden="true" className="text-muted-foreground size-4" />
          <span className="sr-only"> to </span>
          <span>{tailored.composite.toFixed(1)}</span>
        </span>
        <DeltaChip value={delta.composite} unit="points" />
        {moved.length > 0 ? (
          <span className="text-muted-foreground min-w-0 text-body-small tabular-nums">
            {moved.map((m, i) => (
              <span key={m.label}>
                {i > 0 ? <span aria-hidden="true"> · </span> : null}
                <span aria-hidden="true">{m.text}</span>
                <span className="sr-only">{i > 0 ? ", " : ""}{m.spoken}</span>
              </span>
            ))}
          </span>
        ) : null}
      </div>
    );
  }

  if (compare.isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (compare.isError) {
    const err = compare.error;
    const recoverable = err instanceof ApiError && err.status === 422;
    const retry = recoverable ? (
      <Button
        variant="outline"
        size="sm"
        onClick={() => rescoreBoth.mutate()}
        disabled={rescoreBoth.isPending || readOnly}
      >
        {rescoreBoth.isPending ? (
          <Loader2 className="animate-spin" />
        ) : (
          <RefreshCw />
        )}
        {rescoreBoth.isPending ? "Updating…" : "Update both scores"}
      </Button>
    ) : null;
    if (bare) {
      return (
        <div className="space-y-3">
          <p className="text-muted-foreground text-body-medium">{couldnt("compare the scores", err)}</p>
          {retry}
        </div>
      );
    }
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Match score before and after</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-muted-foreground text-body-medium">{couldnt("compare the scores", err)}</p>
          {retry}
        </CardContent>
      </Card>
    );
  }

  const data = compare.data;
  if (!data) return null;

  const deltaPts = data.delta.composite;
  // Gained first, then Lost, then Same; the sort is stable, so each group keeps the server's order.
  const skillRows = data.skill_diff
    .map((row) => ({ row, change: changeOf(row.before, row.after) }))
    .sort((a, b) => CHANGE_ORDER[a.change] - CHANGE_ORDER[b.change]);

  const updateScore = (
    <Button
      variant="outline"
      size="sm"
      className="shrink-0"
      onClick={() => rescoreTailored.mutate()}
      disabled={rescoring || readOnly}
    >
      <RefreshCw
        className={rescoring ? "animate-spin" : undefined}
      />
      {rescoring ? "Updating…" : "Update score"}
    </Button>
  );
  const headline = (
    <div className="flex items-baseline gap-2 text-headline-small tabular-nums">
      <span className="text-muted-foreground">
        {data.base.composite.toFixed(1)}
      </span>
      <MoveRight className="text-muted-foreground size-4 self-center" />
      <span>{data.tailored.composite.toFixed(1)}</span>
      <DeltaChip value={deltaPts} unit="points" className="self-center" />
    </div>
  );
  const details = (
    <>
      <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {SUBSCORE_LABELS.map(({ key, label }) => (
          <DeltaBar
            key={key}
            label={label}
            value={data.delta.subscores[key] ?? 0}
          />
        ))}
      </div>

      {data.skill_diff.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Skill</TableHead>
              <TableHead>Change</TableHead>
              <TableHead>Now</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {skillRows.map(({ row, change }) => (
              <TableRow key={row.jd_skill}>
                <TableCell className="font-medium whitespace-normal">{row.jd_skill}</TableCell>
                <TableCell className="whitespace-normal">
                  <ChangeCell change={change} />
                </TableCell>
                <TableCell className="whitespace-normal">
                  <SkillNowCell row={row.after} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="text-muted-foreground text-body-medium">
          No skill changes.
        </p>
      )}
    </>
  );

  if (bare) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {headline}
          {updateScore}
        </div>
        {details}
      </div>
    );
  }

  return (
    <Card>
      {/* Wraps: at 375 the title kept one word per line beside the button. */}
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-2">
        <CardTitle>Match score before and after</CardTitle>
        {updateScore}
      </CardHeader>
      <CardContent className="space-y-4">
        {headline}
        {details}
      </CardContent>
    </Card>
  );
}
