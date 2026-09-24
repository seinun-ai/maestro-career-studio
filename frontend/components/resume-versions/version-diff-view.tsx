"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { getResumeVersion } from "@/lib/api";
import { diffChangeWords } from "@/lib/describe-edit";
import { cn } from "@/lib/utils";
import type { ResumeDiffChange } from "@/lib/types";

const KIND_STYLES: Record<ResumeDiffChange["kind"], string> = {
  added: "bg-emerald-500/10 text-emerald-800 dark:text-emerald-400",
  removed: "bg-destructive/10 text-destructive",
  modified: "bg-amber-500/10 text-amber-800 dark:text-amber-400",
};

const KIND_LABELS: Record<ResumeDiffChange["kind"], string> = {
  added: "Added",
  removed: "Removed",
  modified: "Updated",
};

export function DiffChangeList({ changes }: { changes: ResumeDiffChange[] }) {
  if (changes.length === 0) {
    return (
      <p className="text-muted-foreground text-sm italic">No changes to the text.</p>
    );
  }
  return (
    <ul className="space-y-2">
      {changes.map((c, i) => {
        // The section in words, and its label only when it says more.
        const words = diffChangeWords(c);
        return (
        <li
          key={i}
          className={cn("rounded-md px-3 py-2 text-sm", KIND_STYLES[c.kind])}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="bg-background/60 text-xs">
              {KIND_LABELS[c.kind]}
            </Badge>
            <span className="font-medium">{words.section}</span>
            {words.label ? (
              <>
                <span className="opacity-80">·</span>
                <span>{words.label}</span>
              </>
            ) : null}
          </div>
          {c.details && c.details.length > 0 && (
            <ul className="mt-1 ml-5 list-disc space-y-0.5 text-xs opacity-90">
              {c.details.map((d, j) => (
                <li key={j}>{d}</li>
              ))}
            </ul>
          )}
        </li>
        );
      })}
    </ul>
  );
}

/** Fetches a version's diff-vs-parent and renders it. */
export function VersionDiffView({
  kind,
  resumeKey,
  version,
}: {
  kind: "base" | "application";
  resumeKey: string;
  version: number;
}) {
  const detail = useQuery({
    queryKey: ["resume-version", kind, resumeKey, version],
    queryFn: () => getResumeVersion(kind, resumeKey, version),
  });

  if (detail.isLoading) {
    return <p className="text-muted-foreground text-sm">Loading changes…</p>;
  }
  if (detail.isError || !detail.data) {
    return <p className="text-destructive text-sm">Couldn&apos;t load this version.</p>;
  }
  return <DiffChangeList changes={detail.data.diff} />;
}
