"use client";

import { PreviewThumbnail } from "@/components/gallery/preview-thumbnail";
import { apiUrlForBrowserPdf } from "@/lib/api";
import type { TemplateSummary } from "@/lib/types";

/** True when the source changed after the last validation, so the preview PDF
 *  on disk — and therefore this thumbnail — shows the PREVIOUS design. */
export function isThumbnailStale(t: TemplateSummary): boolean {
  if (!t.validated_at || !t.updated_at) return false;
  // 1s slack: validate_template writes the row and stamps validated_at in the
  // same transaction, so updated_at is a hair later on a freshly validated row.
  return Date.parse(t.updated_at) > Date.parse(t.validated_at) + 1000;
}

/**
 * Page 1 of the template's validated preview, rendered from the synthetic
 * sample resume (never the user's data).
 *
 * A template that has never validated has no preview PDF on disk, so it gets a
 * placeholder rather than a broken <img> — "no preview yet" and "preview
 * failed" must not look the same.
 */
export function TemplateThumbnail({
  template,
  className,
}: {
  template: TemplateSummary;
  className?: string;
}) {
  // Cache-bust on validated_at: re-validating regenerates the preview PDF at
  // the same URL, so without this the stale image sticks.
  const src =
    template.status === "ready" && template.validated_at
      ? apiUrlForBrowserPdf(
          `/api/templates/${template.id}/preview/page/1?v=${encodeURIComponent(
            template.validated_at,
          )}`,
        )
      : null;

  return (
    <PreviewThumbnail
      src={src}
      alt={`${template.display_name ?? template.id} preview`}
      placeholder="Not validated"
      chip={
        isThumbnailStale(template)
          ? {
              label: "needs re-validation",
              title:
                "Edited since its last validation, so the preview shows the previous design. Use Re-validate in the card menu to refresh.",
            }
          : undefined
      }
      className={className}
    />
  );
}
