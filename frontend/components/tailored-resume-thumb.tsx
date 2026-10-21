"use client";

import { PreviewThumbnail } from "@/components/gallery/preview-thumbnail";
import { ResumeTag } from "@/components/visual";
import { apiUrlForBrowserPdf } from "@/lib/api";
import { resumeColorStyle } from "@/lib/resume-color";
import type { Application } from "@/lib/types";

/**
 * The job's resume on step 4's lead card, drawn like a base resume card (owner decision D2: the base resume's
 * square belongs on this card): the 6px band in the resume's colour, page 1 of the application's PDF ("No PDF
 * yet" until step 3 makes one), then the resume's name with its square on the resume's tint. The image is
 * cache-busted on the application's `updated_at`, which every render of the PDF moves.
 */
export function TailoredResumeThumb({
  app,
  hue,
  name,
  tailored,
}: {
  app: Pick<Application, "id" | "pdf_path" | "updated_at">;
  hue: number | null | undefined;
  /** The base resume's name. */
  name: string;
  /** A tailored score exists for the application (the standing line's own word). */
  tailored: boolean;
}) {
  const label = tailored ? `${name}, tailored` : name;
  const src = app.pdf_path
    ? apiUrlForBrowserPdf(`/api/applications/${app.id}/preview/page/1?v=${encodeURIComponent(app.updated_at)}`)
    : null;
  return (
    <div style={resumeColorStyle(hue)} className="flex w-[220px] flex-col overflow-hidden rounded-corner-md bg-surface-container">
      <div aria-hidden="true" className="h-1.5 shrink-0 bg-resume" />
      {/* Square-topped: the band above is the card's top edge. */}
      <PreviewThumbnail src={src} alt={`${label}, page 1`} placeholder="No PDF yet" className="rounded-none border-b-0" />
      <div className="bg-resume-container px-3.5 py-3 text-label-large text-on-resume-container">
        <ResumeTag hue={hue} className="max-w-full min-w-0">
          <span className="truncate" title={label}>{label}</span>
        </ResumeTag>
      </div>
    </div>
  );
}
