"use client";

import type { ReactNode } from "react";
import { Download, ExternalLink, FileText } from "lucide-react";

import { IconButton } from "@/components/icon-button";
import { ShowCopyButton } from "@/components/resumes-folder-actions";
import { apiUrlForBrowserPdf } from "@/lib/api";
import type { Application } from "@/lib/types";

/**
 * The application's PDF as one line on `surface-container-low`: the file name, its pages, then Download PDF, Open
 * PDF in new tab and Show in Finder as icon buttons; step 3 adds the resumes folder line and Update PDF. Only for
 * an application with a PDF (step 4 shows no PDF line: step 3 holds it).
 */
export function PdfFileLine({
  app,
  note,
  actions,
}: {
  app: Application;
  note?: ReactNode;
  actions?: ReactNode;
}) {
  const pdfHref = apiUrlForBrowserPdf(`/api/applications/${app.id}/pdf`);
  const pdfFilename = app.pdf_path?.split(/[\\/]/).pop() ?? "tailored-resume.pdf";
  const pages = app.pdf_pages ? `${app.pdf_pages} ${app.pdf_pages === 1 ? "page" : "pages"}` : null;
  return (
    <div className="bg-surface-container-low flex flex-wrap items-center gap-x-2 gap-y-1 rounded-corner-md py-2 pr-2 pl-4">
      <FileText aria-hidden="true" className="text-muted-foreground size-4 shrink-0" />
      <span className="min-w-0 truncate text-title-small" title={pdfFilename}>
        {pdfFilename}
      </span>
      {pages ? (
        <span className="text-muted-foreground text-body-small">
          <span aria-hidden="true">· </span>
          {pages}
        </span>
      ) : null}
      {note}
      <div className="ml-auto flex items-center gap-1">
        <IconButton
          label="Download PDF"
          icon={<Download className="size-4" />}
          nativeButton={false}
          render={<a href={pdfHref} download={pdfFilename} />}
        />
        <IconButton
          label="Open PDF in new tab"
          icon={<ExternalLink className="size-4" />}
          nativeButton={false}
          render={<a href={pdfHref} target="_blank" rel="noopener noreferrer" />}
        />
        <ShowCopyButton applicationId={app.id} variant="ghost" iconOnly />
        {actions}
      </div>
    </div>
  );
}
