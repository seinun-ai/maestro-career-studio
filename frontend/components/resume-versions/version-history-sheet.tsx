"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { VersionDiffView } from "@/components/resume-versions/version-diff-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { listResumeVersions, restoreResumeVersion } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ResumeVersion, ResumeVersionSource } from "@/lib/types";

const SOURCE_LABELS: Record<ResumeVersionSource, string> = {
  create: "Created",
  form_edit: "Manual edit",
  edit_ops: "Edit",
  chat: "Chat",
  tailor: "Tailored",
  import: "Import",
  restore: "Restore",
};

const SOURCE_BADGE: Partial<Record<ResumeVersionSource, string>> = {
  chat: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  tailor: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  restore: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
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
}: {
  kind: "base" | "application";
  resumeKey: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRestored?: () => void;
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

  const restore = useMutation({
    mutationFn: (version: number) => restoreResumeVersion(kind, resumeKey, version),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["resume-versions", kind, resumeKey] });
      qc.invalidateQueries({ queryKey: ["base-resumes"] });
      qc.invalidateQueries({ queryKey: ["application"] });
      setSelected(null);
      toast.success(`Restored as version ${created.version_number}`);
      onRestored?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const requestRestore = async (v: ResumeVersion) => {
    const ok = await confirm({
      title: `Restore version ${v.version_number}?`,
      description:
        "Restoring adds a new version on top. Nothing is lost.",
      confirmLabel: "Restore",
    });
    if (ok) restore.mutate(v.version_number);
  };

  const latestNumber = versions.data?.[0]?.version_number;

  const renderVersion = (v: ResumeVersion, indent = false) => (
    <li key={v.id} className={cn(indent && "ml-4")}>
      <button
        type="button"
        onClick={() => setSelected(selected === v.version_number ? null : v.version_number)}
        className={cn(
          "hover:bg-accent w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
          selected === v.version_number && "border-primary bg-accent",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs">v{v.version_number}</span>
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
              <span className="text-muted-foreground text-xs">current</span>
            )}
          </div>
          <span className="text-muted-foreground shrink-0 text-xs">
            {new Date(v.created_at).toLocaleString()}
          </span>
        </div>
        {v.summary && (
          <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
            {v.summary}
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
      <SheetContent side="right" className="w-full">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <History className="size-4" /> Version history
          </SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {versions.isLoading && (
            <p className="text-muted-foreground text-sm">Loading…</p>
          )}
          {versions.isError && (
            <p className="text-destructive text-sm">Could not load history.</p>
          )}
          {versions.data?.length === 0 && (
            <p className="text-muted-foreground text-sm">
              No versions yet. Save an edit to start the history.
            </p>
          )}
          <ul className="space-y-2 pb-4">
            {rows.map((row, i) => {
              if (row.type === "version") return renderVersion(row.version);
              const expanded = expandedGroups.has(i);
              return (
                <li key={`group-${i}`}>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground w-full rounded-md border border-dashed px-3 py-2 text-left text-xs"
                    onClick={() =>
                      setExpandedGroups((s) => {
                        const next = new Set(s);
                        if (next.has(i)) next.delete(i);
                        else next.add(i);
                        return next;
                      })
                    }
                  >
                    {expanded ? "▾" : "▸"} {row.versions.length} manual edits (v
                    {row.versions[row.versions.length - 1].version_number}–v
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
