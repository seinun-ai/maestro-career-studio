"use client";

import type { ReactNode } from "react";

import {
  GalleryCard,
  GalleryCardActions,
  GalleryGrid,
} from "@/components/gallery/gallery-card";
import { HealthListChip } from "@/components/resume-health/health-badges";
import { Badge } from "@/components/ui/badge";
import { CardHeader, CardTitle } from "@/components/ui/card";
import { formatAbsoluteDateTime, formatLabeledAgo } from "@/lib/format-date";
import { ResumeSwatch } from "@/components/visual";
import { displayRoleTag, useRoleCategories } from "@/components/role-category-picker";
import { groupByRole, isRoleUnset, type RoleGroup } from "@/lib/role-groups";
import { resumeColorStyle } from "@/lib/resume-color";
import { cn } from "@/lib/utils";
import { baseResumeLabel, type BaseResumeSummary } from "@/lib/types";

import { AnchorPills, ON_TINT_PILL_CLASS } from "./anchor-pills";
import { BaseResumeThumbnail } from "./base-resume-thumbnail";

/**
 * A 6px band in the resume's color, the full-size thumbnail, then a footer tinted in the same color with
 * the name (led by the color's square), last-edited, what its Target sets and the actions menu. The card
 * root carries the color's CSS variables, so the band, the footer and the square all follow one hue.
 *
 * The role is the group's heading, so a card carries no role pill; an unset role is the "Role not set" group,
 * whose heading carries the one hint for fixing it.
 */
function BaseResumeCardBody({
  resume,
  actions,
}: {
  resume: BaseResumeSummary;
  actions?: ReactNode;
}) {
  const isArchived = !!resume.archived_at;
  const roleUnset = isRoleUnset(resume);
  const name = baseResumeLabel(resume.slug, [resume]);
  const { data: options } = useRoleCategories();
  const role = roleUnset ? null : displayRoleTag(resume.role_category, resume.role_label, options);

  return (
    <>
      {/* An archived card fades only what is picture: the band and the page image. The footer's words stay at full
          contrast (the Archived pill says the state), where fading the whole card dropped them to about 3:1. */}
      <div aria-hidden="true" className={cn("h-1.5 shrink-0 bg-resume", isArchived && "opacity-60")} />
      {/* Square-topped: the band above is the card's top edge, and a rounded thumbnail would show the card behind it. */}
      <BaseResumeThumbnail resume={resume} className={cn("rounded-none", isArchived && "[&_img]:opacity-60")} />
      <CardHeader className="rounded-none bg-resume-container py-4 text-on-resume-container">
        <div className="flex min-w-0 flex-col gap-2">
          {/* The slug is never shown, not even on hover: the resume is named
              by its display name (or the slug's words), and the card links to
              /base-resumes/<slug> whenever you actually need it. */}
          <CardTitle
            className="flex min-w-0 items-center gap-1.5"
            title={role ? `${name}\n${role}` : name}
          >
            <ResumeSwatch hue={resume.color_hue} />
            <span className="truncate">{name}</span>
          </CardTitle>
          {/* Timestamp and menu share this row, so the menu costs no extra
              height and lands at the card's bottom-right. */}
          <div className="flex items-end gap-2">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-body-small">
              <span title={formatAbsoluteDateTime(resume.updated_at)}>
                {formatLabeledAgo(resume.updated_at, "Updated")}
              </span>
              <HealthListChip slug={resume.slug} />
              {/* The default secondary fill is the tint's own tone and would vanish on it: the card fill shows. */}
              {isArchived && (
                <Badge variant="secondary" className={ON_TINT_PILL_CLASS}>
                  Archived
                </Badge>
              )}
              <AnchorPills resume={resume} showRole={false} onTint />
            </div>
            {actions && <GalleryCardActions>{actions}</GalleryCardActions>}
          </div>
        </div>
      </CardHeader>
    </>
  );
}

function RoleSection({
  group,
  href,
  renderActions,
}: {
  group: RoleGroup<BaseResumeSummary>;
  href: (r: BaseResumeSummary) => string;
  renderActions?: (r: BaseResumeSummary) => ReactNode;
}) {
  return (
    // A plain div: the heading names the group for a screen reader, and a region per group would add landmarks.
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-title-small">
          {group.label ?? "Role not set"}
        </h2>
        <span className="text-label-small text-muted-foreground">
          {group.resumes.length}
          <span className="sr-only">{group.resumes.length === 1 ? " resume" : " resumes"}</span>
        </span>
        {/* The heading already says "Role not set", so a card does not repeat it; the way out is said once, here. */}
        {group.label === null && (
          <span className="text-body-small text-muted-foreground">Set a role in each resume&apos;s Target to group it.</span>
        )}
      </div>
      <GalleryGrid>
        {group.resumes.map((r) => (
          <GalleryCard
            key={r.slug}
            href={href(r)}
            ariaLabel={`Open ${r.display_name ?? r.slug}`}
            // The footer runs to the card's bottom edge, so the card's own bottom padding and row gap go.
            className="gap-0 pb-0"
            style={resumeColorStyle(r.color_hue)}
          >
            <BaseResumeCardBody resume={r} actions={renderActions?.(r)} />
          </GalleryCard>
        ))}
      </GalleryGrid>
    </div>
  );
}

/** The cards, under a plain heading per role. */
export function BaseResumeGallery({
  resumes,
  href,
  renderActions,
}: {
  resumes: BaseResumeSummary[];
  /** The whole card opens this. Replaces an Edit button. */
  href: (r: BaseResumeSummary) => string;
  /** The corner menu. Rendered ABOVE the stretched link. */
  renderActions?: (r: BaseResumeSummary) => ReactNode;
}) {
  const { data: options } = useRoleCategories();
  const labelOf = (r: BaseResumeSummary) => displayRoleTag(r.role_category, r.role_label, options);
  return (
    <div className="flex flex-col gap-6">
      {groupByRole(resumes, labelOf).map((group) => (
        <RoleSection key={group.key} group={group} href={href} renderActions={renderActions} />
      ))}
    </div>
  );
}
