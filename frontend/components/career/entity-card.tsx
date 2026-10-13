"use client";

import { useState } from "react";
import { ArrowUpRight, Ellipsis, ListChecks, Merge } from "lucide-react";

import { kbStatusLabel } from "@/components/career/career-labels";
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
import { ResumeSwatch } from "@/components/visual";
import { useBaseResumeColor, useBaseResumeLabel } from "@/hooks/use-base-resume-label";
import { formatAbsoluteDateTime, formatTimeAgo } from "@/lib/format-date";
import type { KBEntityStatus, KBEntitySummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CONCEPT_ICONS } from "@/lib/concept-icons";

const DraftsIcon = CONCEPT_ICONS.drafts;

// Colours only: the words come from career-labels (one table for every surface). A completed item
// carries no chip: its dates already say it, and a chip on nearly every card is noise.
const STATUS_STYLES: Record<Exclude<KBEntityStatus, "completed">, { chip: string; dot: string }> = {
  ongoing: {
    chip: "bg-primary-container text-on-primary-container",
    dot: "bg-primary",
  },
  archived: {
    chip: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
};

export function EntityCard({ entity }: { entity: KBEntitySummary }) {
  const status =
    entity.status === "completed"
      ? null
      : (STATUS_STYLES[entity.status] ?? {
          chip: "bg-muted text-muted-foreground",
          dot: "bg-muted-foreground/50",
        });
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
      className="h-full bg-surface-container-low pt-4 ring-0 transition-[translate,scale,background-color,box-shadow] duration-150 ease-out hover:-translate-y-0.5 hover:bg-primary/5 has-[a:focus-visible]:ring-3 has-[a:focus-visible]:ring-ring has-[a:active]:scale-[0.97]"
    >
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
        <div className="min-w-0">
          <CardTitle className="truncate">{entity.title}</CardTitle>
          {/* No organization and no dates: no second line. Independent was
              a claim the user never made. */}
          {entity.org || dateRange ? (
            <p className="text-muted-foreground mt-0.5 truncate text-body-medium">
              {entity.org || dateRange}
            </p>
          ) : null}
          {entity.org && dateRange ? (
            <p className="text-muted-foreground mt-0.5 truncate text-body-small">{dateRange}</p>
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
                    <Ellipsis className="size-3.5" />
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
        <div className="flex flex-wrap items-center gap-2 text-body-small empty:hidden">
          {status ? (
            <span
              className={cn(
                "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-label-medium",
                status.chip,
              )}
            >
              <span className={cn("size-1.5 rounded-full", status.dot)} />
              {kbStatusLabel(entity.status)}
            </span>
          ) : null}
          <Metric icon={ListChecks} value={entity.point_count} one="bullet" many="bullets" />
          <Metric icon={DraftsIcon} value={entity.draft_count} one="draft" many="drafts" />
          <Metric icon={CONCEPT_ICONS.attachment} value={entity.document_count} one="document" many="documents" />
        </div>
        <p
          className="text-muted-foreground text-body-small"
          title={formatAbsoluteDateTime(entity.last_activity)}
        >
          Updated {formatTimeAgo(entity.last_activity)}
        </p>
        <UsedIn slugs={entity.used_in_bases ?? []} />
      </CardContent>

      <MergeEntityDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        source={entity}
      />
    </GalleryCard>
  );
}

/** The squares drawn before "+N" takes the rest. */
const MAX_SQUARES = 8;

/** "In 3 resumes" and the resumes' squares: which base resumes this item is on. A square always sits
 *  beside its name, so for a row of squares the names ride in the row's title and in an sr-only list
 *  (the squares themselves are hidden from assistive tech). Nothing for an item that is on none. */
function UsedIn({ slugs }: { slugs: string[] }) {
  const colorOf = useBaseResumeColor();
  const nameOf = useBaseResumeLabel();
  if (slugs.length === 0) return null;
  const names = slugs.map(nameOf);
  return (
    <div className="text-muted-foreground flex items-center gap-1.5 text-body-small" title={names.join(", ")}>
      <span>
        In {slugs.length} {slugs.length === 1 ? "resume" : "resumes"}
      </span>
      <span className="flex items-center gap-1" aria-hidden="true">
        {slugs.slice(0, MAX_SQUARES).map((slug) => (
          <ResumeSwatch key={slug} hue={colorOf(slug)} />
        ))}
        {slugs.length > MAX_SQUARES ? <span>+{slugs.length - MAX_SQUARES}</span> : null}
      </span>
      <ul className="sr-only">
        {names.map((name, i) => (
          <li key={slugs[i]}>{name}</li>
        ))}
      </ul>
    </div>
  );
}

/** A count and its noun, in agreement: "1 bullet", "3 bullets". Nothing for zero: an empty count is not a fact. */
function Metric({
  icon: Icon,
  value,
  one,
  many,
}: {
  icon: typeof ListChecks;
  value: number;
  one: string;
  many: string;
}) {
  if (value === 0) return null;
  return (
    <span className="text-muted-foreground inline-flex h-6 items-center gap-1 rounded-full bg-surface-container px-2">
      <Icon className="size-3.5" aria-hidden="true" />
      {value} {value === 1 ? one : many}
    </span>
  );
}
