"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, History, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { LoadErrorState } from "@/components/load-error-state";
import { VersionDiffView } from "@/components/resume-versions/version-diff-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { listResumeVersions, restoreResumeVersion } from "@/lib/api";
import { versionSummaryWords } from "@/lib/describe-edit";
import { couldnt, loadErrorDetail } from "@/lib/error-text";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import { isLoadFailure } from "@/lib/query-state";
import { notifyRenderOutcome } from "@/lib/render-note";
import { cn } from "@/lib/utils";
import type { ResumeVersion, ResumeVersionSource } from "@/lib/types";

const SOURCE_LABELS: Record<ResumeVersionSource, string> = {
  create: "Created",
  form_edit: "Your edit",
  edit_ops: "Suggested edit",
  chat: "Assistant",
  tailor: "Tailored",
  import: "Imported",
  restore: "Restored",
};

const SOURCE_BADGE: Partial<Record<ResumeVersionSource, string>> = {
  chat: "bg-violet-500/10 text-violet-800 dark:text-violet-400",
  tailor: "bg-blue-500/10 text-blue-800 dark:text-blue-400",
  restore: "bg-amber-500/10 text-amber-800 dark:text-amber-400",
};

/** Consecutive manual saves collapse into one expandable group (Figma-style). */
type HistoryRow =
  | { type: "version"; version: ResumeVersion }
  | { type: "group"; versions: ResumeVersion[] };

function groupVersions(versions: ResumeVersion[]): HistoryRow[] {
  const rows: HistoryRow[] = [];
  let run: ResumeVersion[] = [];
  const flush = () => {
    if (run.length === 0) return;
    if (run.length === 1) rows.push({ type: "version", version: run[0] });
    else rows.push({ type: "group", versions: run });
    run = [];
  };
  for (const v of versions) {
    if (v.source === "form_edit" && !v.label) {
      run.push(v);
    } else {
      flush();
      rows.push({ type: "version", version: v });
    }
  }
  flush();
  return rows;
}

export function VersionHistorySheet({
  kind,
  resumeKey,
  open,
  onOpenChange,
  onRestored,
  finalFocus,
}: {
  kind: "base" | "application";
  resumeKey: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRestored?: () => void;
  /** Where focus returns on close; the studios pass their ⋯ trigger. */
  finalFocus?: RefObject<HTMLElement | null>;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [selected, setSelected] = useState<number | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());

  const versions = useQuery({
    queryKey: ["resume-versions", kind, resumeKey],
    queryFn: () => listResumeVersions(kind, resumeKey),
    enabled: open,
  });

  const rows = useMemo(
    () => groupVersions(versions.data ?? []),
    [versions.data],
  );

  // Restore closes the open row, and its button with it. The sheet stays
  // open, so focus goes to the version the restore just added, once the list
  // shows it (never to <body>).
  const listRef = useRef<HTMLUListElement>(null);
  const landOn = useRef<number | null>(null);
  useEffect(() => {
    const target = landOn.current;
    if (target == null) return;
    const row = listRef.current?.querySelector<HTMLElement>(`[data-version="${target}"]`);
    if (!row) return;
    landOn.current = null;
    // The Restore button is gone: focus that fell to <body> or to the sheet
    // itself (its focus trap catches it), or that the confirm handed back to
    // the restored row, goes to the new version.
    const active = document.activeElement;
    const ours = !active || active === document.body || active.contains(row) || listRef.current?.contains(active);
    if (ours) row.focus({ preventScroll: true });
  }, [versions.data]);

  const restore = useMutation({
    mutationFn: (version: number) => restoreResumeVersion(kind, resumeKey, version),
    onSuccess: (created) => {
      landOn.current = created.version_number;
      qc.invalidateQueries({ queryKey: ["resume-versions", kind, resumeKey] });
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      setSelected(null);
      // The restore is committed before the re-render, so a render failure
      // comes back beside the success, not instead of it. Only a base restore
      // renders at all; an application restore has no PDF to keep.
      notifyRenderOutcome(created, { staleLabel: "The resume" });
      toast.success(`Restored as Version ${created.version_number}`);
      onRestored?.();
    },
    onError: (err: Error) => toast.error(couldnt("restore the version", err)),
  });
  // One restore per gesture: a second confirmed restore added a second version.
  const restoreOnce = useSingleFlight(restore.mutate);

  const requestRestore = async (v: ResumeVersion) => {
    const ok = await confirm({
      title: `Restore Version ${v.version_number}?`,
      description:
        "Restoring adds a new version on top. Nothing is lost.",
      confirmLabel: "Restore",
      // Back to the version's own row: the Restore button leaves with it.
      returnFocus: () =>
        listRef.current?.querySelector<HTMLElement>(`[data-version="${v.version_number}"]`) ?? null,
    });
    if (ok) restoreOnce(v.version_number);
  };

  const latestNumber = versions.data?.[0]?.version_number;

  const renderVersion = (v: ResumeVersion, indent = false) => (
    <li key={v.id} className={cn(indent && "ml-4")}>
      <button
        type="button"
        data-version={v.version_number}
        onClick={() => setSelected(selected === v.version_number ? null : v.version_number)}
        className={cn(
          "hover:bg-accent w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
          selected === v.version_number && "border-primary bg-accent",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Version {v.version_number}</span>
            <Badge
              variant="secondary"
              className={cn("text-xs", SOURCE_BADGE[v.source])}
            >
              {SOURCE_LABELS[v.source] ?? v.source}
            </Badge>
            {v.label && (
              <Badge variant="outline" className="text-xs">
                {v.label}
              </Badge>
            )}
            {v.version_number === latestNumber && (
              <span className="text-muted-foreground text-xs">Current</span>
            )}
          </div>
          <span className="text-muted-foreground shrink-0 text-xs">
            {formatAbsoluteDateTime(v.created_at)}
          </span>
        </div>
        {v.summary && (
          <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
            {versionSummaryWords(v.summary)}
          </p>
        )}
      </button>
      {selected === v.version_number && (
        <div className="bg-muted/40 mt-1 rounded-md border p-3">
          <VersionDiffView kind={kind} resumeKey={resumeKey} version={v.version_number} />
          {v.version_number !== latestNumber && (
            <div className="mt-3 flex justify-end">
              <Button
                size="sm"
                variant="outline"
                disabled={restore.isPending}
                onClick={() => requestRestore(v)}
                // Disables itself while restoring: a native `disabled` drops focus.
                focusableWhenDisabled
                className="data-disabled:pointer-events-none data-disabled:opacity-50"
              >
                <RotateCcw className="mr-1 size-3.5" />
                {restore.isPending ? "Restoring…" : "Restore this version"}
              </Button>
            </div>
          )}
        </div>
      )}
    </li>
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full" finalFocus={finalFocus}>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <History className="size-4" /> Version history
          </SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {/* A retry refetches from "pending": the failure branch holds (and
              keeps Try again focused) until it answers. */}
          {versions.isLoading && !isLoadFailure(versions) && (
            <p className="text-muted-foreground text-sm">Loading…</p>
          )}
          {isLoadFailure(versions) && (
            <LoadErrorState
              title="Couldn't load Version history."
              detail={loadErrorDetail(versions.error)}
              retrying={versions.isFetching}
              onRetry={() => void versions.refetch()}
            />
          )}
          {versions.data?.length === 0 && (
            <p className="text-muted-foreground text-sm">
              No versions yet. Save an edit to start the history.
            </p>
          )}
          <ul ref={listRef} className="space-y-2 pb-4">
            {rows.map((row, i) => {
              if (row.type === "version") return renderVersion(row.version);
              const expanded = expandedGroups.has(i);
              return (
                <li key={`group-${i}`}>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    className="text-muted-foreground hover:text-foreground flex w-full items-center gap-1 rounded-md border border-dashed px-3 py-2 text-left text-xs"
                    onClick={() =>
                      setExpandedGroups((s) => {
                        const next = new Set(s);
                        if (next.has(i)) next.delete(i);
                        else next.add(i);
                        return next;
                      })
                    }
                  >
                    {expanded ? (
                      <ChevronDown className="size-3.5" aria-hidden="true" />
                    ) : (
                      <ChevronRight className="size-3.5" aria-hidden="true" />
                    )}
                    {row.versions.length} edits (Versions{" "}
                    {row.versions[row.versions.length - 1].version_number} to{" "}
                    {row.versions[0].version_number})
                  </button>
                  {expanded && (
                    <ul className="mt-2 space-y-2">
                      {row.versions.map((v) => renderVersion(v, true))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </SheetContent>
    </Sheet>
  );
}
