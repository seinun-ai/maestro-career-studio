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
import { roleLabel } from "@/components/role-category-picker";
import type { BaseResumeSummary } from "@/lib/types";

import { BaseResumeThumbnail } from "./base-resume-thumbnail";

/**
 * Thumbnail, name, last-edited and the actions menu. Nothing else.
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

  return (
    <>
      <BaseResumeThumbnail resume={resume} />
      <CardHeader>
        <div className="flex min-w-0 flex-col gap-2">
          {/* The slug is NOT a visible line: for a resume created without a
              display name it printed the same string twice, once as the title
              and once below it. It stays one hover away, and the card links to
              /base-resumes/<slug> whenever you actually need it. */}
          <CardTitle
            className="min-w-0 truncate text-base"
            title={[
              resume.display_name && resume.display_name !== resume.slug
                ? `${resume.display_name} · ${resume.slug}`
                : resume.slug,
              roleLabel(resume.role_category),
            ].join("\n")}
          >
            {resume.display_name ?? resume.slug}
          </CardTitle>
          {/* Timestamp and menu share this row, so the menu costs no extra
              height and lands at the card's bottom-right. */}
          <div className="flex items-end gap-2">
            <div className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
              <span title={formatAbsoluteDateTime(resume.updated_at)}>
                {formatLabeledAgo(resume.updated_at, "Updated")}
              </span>
              <HealthListChip slug={resume.slug} />
              {isArchived && <Badge variant="secondary">Archived</Badge>}
              {roleUnset && (
                <Badge
                  variant="outline"
                  title="This resume has no target role, so it is missing from role-based grouping. Set one in the editor."
                >
                  Role not set
                </Badge>
              )}
            </div>
            {actions && <GalleryCardActions>{actions}</GalleryCardActions>}
          </div>
        </div>
      </CardHeader>
    </>
  );
}

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
  return (
    <GalleryGrid>
      {resumes.map((r) => (
        <GalleryCard
          key={r.slug}
          href={href(r)}
          ariaLabel={`Open ${r.display_name ?? r.slug}`}
          className={r.archived_at ? "opacity-60" : undefined}
        >
          <BaseResumeCardBody resume={r} actions={renderActions?.(r)} />
        </GalleryCard>
      ))}
    </GalleryGrid>
  );
}
