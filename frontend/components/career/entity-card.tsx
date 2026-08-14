import Link from "next/link";
import { ArrowUpRight, BookOpen, FileText, ListChecks } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatAbsoluteDateTime, formatTimeAgo } from "@/lib/format-date";
import type { KBEntityStatus, KBEntitySummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<KBEntityStatus, { label: string; chip: string; dot: string }> = {
  ongoing: {
    label: "Ongoing",
    chip: "bg-blue-600/10 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
    dot: "bg-blue-600 dark:bg-blue-400",
  },
  completed: {
    label: "Completed",
    chip: "bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
  },
  archived: {
    label: "Archived",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
};

const KIND_LABELS: Record<KBEntitySummary["kind"], string> = {
  experience: "Experience",
  project: "Project",
  education: "Education",
  certification: "Certification",
  extra: "Custom section",
};

export function EntityCard({ entity }: { entity: KBEntitySummary }) {
  const status = STATUS_STYLES[entity.status] ?? {
    label: entity.status || "Unknown",
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/50",
  };
  const dateRange = [entity.start_date, entity.end_date].filter(Boolean).join(" – ");

  return (
    <Link
      href={`/career/${entity.id}`}
      className="group rounded-2xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      aria-label={`Open ${entity.title}`}
    >
      <Card className="h-full border-0 bg-muted/45 shadow-none ring-0 transition-[transform,background-color,box-shadow] duration-150 ease-out group-hover:-translate-y-0.5 group-hover:bg-primary/5 group-hover:shadow-sm group-active:scale-[0.97]">
        <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
          <div className="min-w-0">
            <p className="text-muted-foreground mb-1 text-[0.7rem] font-medium uppercase tracking-[0.14em]">
              {entity.kind === "extra" && entity.section_title
                ? entity.section_title
                : KIND_LABELS[entity.kind]}
            </p>
            <CardTitle className="truncate">{entity.title}</CardTitle>
            <p className="text-muted-foreground mt-0.5 truncate text-sm">
              {entity.org || dateRange || "Independent"}
            </p>
            {entity.org && dateRange ? (
              <p className="text-muted-foreground mt-0.5 truncate text-xs">{dateRange}</p>
            ) : null}
          </div>
          <ArrowUpRight
            className="text-muted-foreground size-4 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 pointer-coarse:opacity-100"
            aria-hidden="true"
          />
        </CardHeader>
        <CardContent className="mt-auto space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span
              className={cn(
                "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 font-medium",
                status.chip,
              )}
            >
              <span className={cn("size-1.5 rounded-full", status.dot)} />
              {status.label}
            </span>
            <Metric icon={ListChecks} value={entity.point_count} label="points" />
            {entity.draft_count > 0 ? (
              <Metric icon={BookOpen} value={entity.draft_count} label="drafts" />
            ) : null}
            <Metric icon={FileText} value={entity.document_count} label="docs" />
          </div>
          <p
            className="text-muted-foreground text-xs"
            title={formatAbsoluteDateTime(entity.last_activity)}
          >
            Updated {formatTimeAgo(entity.last_activity)}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

function Metric({
  icon: Icon,
  value,
  label,
}: {
  icon: typeof ListChecks;
  value: number;
  label: string;
}) {
  return (
    <span className="text-muted-foreground inline-flex h-6 items-center gap-1 rounded-full bg-background/70 px-2">
      <Icon className="size-3.5" aria-hidden="true" />
      {value} {label}
    </span>
  );
}
