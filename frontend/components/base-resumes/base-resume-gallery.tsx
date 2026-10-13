"use client";

import { useId, type ReactNode } from "react";

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
import { displayRoleTag, roleLabel, useRoleCategories } from "@/components/role-category-picker";
import { resumeColorStyle } from "@/lib/resume-color";
import { cn } from "@/lib/utils";
import { baseResumeLabel, type BaseResumeSummary, type RoleCategory } from "@/lib/types";

import { AnchorPills } from "./anchor-pills";
import { BaseResumeThumbnail } from "./base-resume-thumbnail";

/**
 * A 6px band in the resume's color, the full-size thumbnail, then a footer tinted in the same color with
 * the name (led by the color's square), last-edited, what its Target sets and the actions menu. The card
 * root carries the color's CSS variables, so the band, the footer and the square all follow one hue.
 *
 * The role badge is CONDITIONAL on purpose: role_category defaults to
 * "unknown", which the model keeps as "a visible state the UI offers to fix".
 * Shown on every card it is decoration; shown only when unset it reports a
 * defect — the same rule the template card's ATS-spacing badge follows.
 */
function BaseResumeCardBody({
  resume,
  actions,
}: {
  resume: BaseResumeSummary;
  actions?: ReactNode;
}) {
  const isArchived = !!resume.archived_at;
  const roleUnset = resume.role_category === "unknown";
  const name = baseResumeLabel(resume.slug, [resume]);

  return (
    <>
      <div aria-hidden="true" className="h-1.5 shrink-0 bg-resume" />
      {/* Square-topped: the band above is the card's top edge, and a rounded thumbnail would show the card behind it. */}
      <BaseResumeThumbnail resume={resume} className="rounded-none" />
      <CardHeader className="rounded-none bg-resume-container py-4 text-on-resume-container">
        <div className="flex min-w-0 flex-col gap-2">
          {/* The slug is never shown, not even on hover: the resume is named
              by its display name (or the slug's words), and the card links to
              /base-resumes/<slug> whenever you actually need it. */}
          <CardTitle
            className="flex min-w-0 items-center gap-1.5"
            title={[name, roleLabel(resume.role_category)].join("\n")}
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
              {/* Card fill and a border in the footer's own text color: the default secondary fill and
                  border are the tint's tone and would vanish on it. */}
              {isArchived && (
                <Badge variant="secondary" className="bg-card text-card-foreground">
                  Archived
                </Badge>
              )}
              {roleUnset && (
                <Badge
                  variant="outline"
                  className="border-on-resume-container/40"
                  title="No target role. Set one in the resume to group it by role."
                >
                  Role not set
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

type RoleGroup = { key: string; label: string | null; resumes: BaseResumeSummary[] };

/** Resumes grouped by their role, in the order each role first appears in `resumes`. A resume with no role
 *  goes in a last group of its own (`label: null`). Archived ones stay in their group. */
function groupByRole(resumes: BaseResumeSummary[], options: RoleCategory[] | undefined): RoleGroup[] {
  const groups = new Map<string, RoleGroup>();
  const unset: RoleGroup = { key: "", label: null, resumes: [] };
  for (const r of resumes) {
    if (r.role_category === "unknown" && !r.role_label) {
      unset.resumes.push(r);
      continue;
    }
    const label = displayRoleTag(r.role_category, r.role_label, options);
    const key = label.toLowerCase();
    const group = groups.get(key) ?? { key, label, resumes: [] };
    group.resumes.push(r);
    groups.set(key, group);
  }
  return [...groups.values(), ...(unset.resumes.length > 0 ? [unset] : [])];
}

function RoleSection({
  group,
  href,
  renderActions,
}: {
  group: RoleGroup;
  href: (r: BaseResumeSummary) => string;
  renderActions?: (r: BaseResumeSummary) => ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <h2 id={headingId} className="text-title-small">
          {group.label ?? "Role not set"}
        </h2>
        <span className="text-label-small text-muted-foreground">
          {group.resumes.length}
          <span className="sr-only">{group.resumes.length === 1 ? " resume" : " resumes"}</span>
        </span>
      </div>
      <GalleryGrid>
        {group.resumes.map((r) => (
          <GalleryCard
            key={r.slug}
            href={href(r)}
            ariaLabel={`Open ${r.display_name ?? r.slug}`}
            // The footer runs to the card's bottom edge, so the card's own bottom padding and row gap go.
            className={cn("gap-0 pb-0", r.archived_at && "opacity-60")}
            style={resumeColorStyle(r.color_hue)}
          >
            <BaseResumeCardBody resume={r} actions={renderActions?.(r)} />
          </GalleryCard>
        ))}
      </GalleryGrid>
    </section>
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
  return (
    <div className="flex flex-col gap-6">
      {groupByRole(resumes, options).map((group) => (
        <RoleSection key={group.key} group={group} href={href} renderActions={renderActions} />
      ))}
    </div>
  );
}
