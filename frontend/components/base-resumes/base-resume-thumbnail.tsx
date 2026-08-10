"use client";

import { PreviewThumbnail } from "@/components/gallery/preview-thumbnail";
import { apiUrlForBrowserPdf } from "@/lib/api";
import type { BaseResumeSummary } from "@/lib/types";

/**
 * Page 1 of the base resume's rendered PDF.
 *
 * NOTE: unlike the template thumbnail, this deliberately does NOT flag
 * staleness by comparing updated_at to the render timestamp. Base resumes
 * re-render on every edit, and the render writes the same row — which trips
 * onupdate=func.now() and leaves updated_at a hair AFTER pdf_rendered_at on
 * every successful render, so that comparison fires on healthy rows. The
 * honest signal is render_error, which resume_ops persists when an auto-render
 * fails instead of returning a 4xx.
 */
export function BaseResumeThumbnail({
  resume,
  className,
}: {
  resume: BaseResumeSummary;
  className?: string;
}) {
  // Cache-bust on pdf_rendered_at: re-rendering regenerates the page image at
  // the same URL, so without this the stale image sticks.
  const src = resume.pdf_rendered_at
    ? apiUrlForBrowserPdf(
        `/api/base-resumes/${resume.slug}/preview/page/1?v=${encodeURIComponent(
          resume.pdf_rendered_at,
        )}`,
      )
    : null;

  return (
    <PreviewThumbnail
      src={src}
      alt={`${resume.display_name ?? resume.slug} preview`}
      placeholder="Not rendered yet"
      chip={
        resume.render_error
          ? {
              label: "Render failed",
              title: `The last render failed, so this preview is the previous version.\n\n${resume.render_error}`,
              className: "text-amber-600 dark:text-amber-400",
            }
          : undefined
      }
      className={className}
    />
  );
}
