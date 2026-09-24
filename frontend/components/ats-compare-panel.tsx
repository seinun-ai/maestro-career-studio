"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MoveRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import { SUBSCORE_LABELS, fixHintLabel, placementLabel } from "@/lib/ats-words";
import { couldnt } from "@/lib/error-text";
import { cn } from "@/lib/utils";
import type { Application, AtsSkillRow } from "@/lib/types";

/** Signed subscore delta (0–1 float) as a green/red bar with a ±points label. */
function DeltaBar({ label, value }: { label: string; value: number }) {
  const pts = value * 100;
  const positive = pts >= 0;
  const width = Math.min(Math.abs(pts), 100);
  return (
    <div className="space-y-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground text-xs">{label}</span>
        <span
          className={cn(
            "text-xs font-medium tabular-nums",
            positive ? "text-emerald-700 dark:text-emerald-400" : "text-destructive",
          )}
        >
          {positive ? "+" : ""}
          {pts.toFixed(1)}
        </span>
      </div>
      <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
        <div
          className={cn(
            "h-full rounded-full transition-[width]",
            positive ? "bg-emerald-500" : "bg-destructive",
          )}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

/** Compact before-and-after cell: matched → where; missing → what would fix it. */
function SkillStateCell({ row }: { row: AtsSkillRow | null }) {
  if (!row) {
    return <span className="text-muted-foreground">—</span>;
  }
  const note = row.matched ? placementLabel(row.placement) : fixHintLabel(row.fix_hint);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {row.matched ? (
        <Badge
          variant="outline"
          className="border-emerald-600/40 text-emerald-700 dark:text-emerald-400"
        >
          Matched
        </Badge>
      ) : (
        <Badge variant="outline" className="text-muted-foreground">
          Missing
        </Badge>
      )}
      {note ? <span className="text-muted-foreground text-xs">{note}</span> : null}
    </span>
  );
}

/**
 * Before-and-after ATS score for a tailored application: the headline score,
 * subscore delta bars, and the per-skill diff. A 422 from the compare
 * endpoint (engine/config version drift between the stored base and tailored
 * rows) is recoverable by scoring both again.
 */
export function AtsComparePanel({
  app,
  jobId,
}: {
  app: Application;
  jobId: string;
}) {
  const qc = useQueryClient();

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
      toast.success("ATS scores updated");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("update the scores", err)),
  });

  const rescoreTailored = useMutation({
    mutationFn: () => runAtsScoreTarget(jobId, "application", app.id, "tailored"),
    onSuccess: () => {
      toast.success("ATS score updated");
      invalidate();
    },
    onError: (err: Error) => toast.error(couldnt("update the score", err)),
  });

  if (compare.isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (compare.isError) {
    const err = compare.error;
    const recoverable = err instanceof ApiError && err.status === 422;
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>ATS score before and after</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-muted-foreground text-sm">{couldnt("compare the scores", err)}</p>
          {recoverable ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => rescoreBoth.mutate()}
              disabled={rescoreBoth.isPending}
            >
              {rescoreBoth.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCw />
              )}
              {rescoreBoth.isPending ? "Updating…" : "Update both scores"}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  const data = compare.data;
  if (!data) return null;

  const deltaPts = data.delta.composite;
  const deltaPositive = deltaPts >= 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <CardTitle>ATS score before and after</CardTitle>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => rescoreTailored.mutate()}
          disabled={rescoreTailored.isPending}
        >
          <RefreshCw
            className={rescoreTailored.isPending ? "animate-spin" : undefined}
          />
          {rescoreTailored.isPending ? "Updating…" : "Update score"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-baseline gap-2 text-2xl font-semibold tabular-nums">
          <span className="text-muted-foreground font-normal">
            {data.base.composite.toFixed(1)}
          </span>
          <MoveRight className="text-muted-foreground size-4 self-center" />
          <span>{data.tailored.composite.toFixed(1)}</span>
          <span
            className={cn(
              "text-sm font-medium",
              deltaPositive ? "text-emerald-700 dark:text-emerald-400" : "text-destructive",
            )}
          >
            ({deltaPositive ? "+" : ""}
            {deltaPts.toFixed(1)})
          </span>
        </div>

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
                <TableHead>Before</TableHead>
                <TableHead>After</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.skill_diff.map((row) => {
                const gained =
                  !(row.before?.matched ?? false) &&
                  (row.after?.matched ?? false);
                const lost =
                  (row.before?.matched ?? false) &&
                  !(row.after?.matched ?? false);
                return (
                  <TableRow
                    key={row.jd_skill}
                    className={cn(
                      gained && "bg-emerald-500/5",
                      lost && "bg-destructive/5",
                    )}
                  >
                    <TableCell className="font-medium whitespace-normal">
                      {row.jd_skill}
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      <SkillStateCell row={row.before} />
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      <SkillStateCell row={row.after} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <p className="text-muted-foreground text-sm">
            No skill changes.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
