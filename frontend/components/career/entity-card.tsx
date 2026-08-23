"use client";

import { useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  FileText,
  ListChecks,
  Merge,
  MoreHorizontal,
} from "lucide-react";

import { MergeEntityDialog } from "@/components/career/merge-entity-dialog";
import { GalleryCard, GalleryCardActions } from "@/components/gallery/gallery-card";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  const [mergeOpen, setMergeOpen] = useState(false);

  return (
    // `GalleryCard` owns the layering this card needs now that it has an
    // actions menu: the link is a z-10 SIBLING covering the face, because an
    // `<a>` wrapping the card would contain the menu and a `<button>` inside an
    // `<a>` is invalid HTML that steals the click. `pt-4` restores the top pad
    // GalleryCard drops for image-first cards — this one leads with text.
    <GalleryCard
      href={`/career/${entity.id}`}
      ariaLabel={`Open ${entity.title}`}
      className="h-full bg-muted/45 pt-4 shadow-none ring-0 transition-[transform,background-color,box-shadow] duration-150 ease-out hover:-translate-y-0.5 hover:bg-primary/5 hover:shadow-sm has-[a:focus-visible]:ring-3 has-[a:focus-visible]:ring-ring/50 has-[a:active]:scale-[0.97]"
    >
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
        <GalleryCardActions>
          <div className="flex items-start gap-0.5">
            <ArrowUpRight
              className="text-muted-foreground mt-1.5 size-4 opacity-0 transition-opacity duration-150 group-hover/card:opacity-100 group-focus-within/card:opacity-100 pointer-coarse:opacity-100"
              aria-hidden="true"
            />
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Actions for ${entity.title}`}
                    className="opacity-0 transition-opacity duration-150 group-hover/card:opacity-100 focus-visible:opacity-100 data-popup-open:opacity-100 pointer-coarse:opacity-100"
                  >
                    <MoreHorizontal className="size-3.5" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setMergeOpen(true)}>
                  <Merge className="size-3.5" /> Merge into…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </GalleryCardActions>
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

      <MergeEntityDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        source={entity}
      />
    </GalleryCard>
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
