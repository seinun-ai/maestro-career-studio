"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";

type Manifest = {
  page_count: number;
  rendered_at: string | null;
  render_error: string | null;
};

/**
 * Clean PDF preview: server-rasterized page PNGs on a neutral surface with a
 * floating page-count pill — replaces the browser's native PDF viewer chrome.
 * `basePath` is e.g. `/api/base-resumes/{slug}` or `/api/applications/{id}`.
 * `version` busts caches whenever the PDF is re-rendered.
 */
export function PdfPagesPreview({
  basePath,
  version,
  emptyMessage,
}: {
  basePath: string;
  version: string | number | null;
  emptyMessage: string;
}) {
  const { data, isError } = useQuery({
    queryKey: ["pdf-preview", basePath, version],
    queryFn: () => apiFetch<Manifest>(`${basePath}/preview/pages`),
    retry: false,
    // The query key includes `version`, so every knob change is a fresh key
    // with no cached entry — without this, `data` goes undefined during the
    // refetch and the empty-state guard below unmounts the whole page stack,
    // flashing the empty message. keepPreviousData holds the prior manifest
    // (and thus the rendered pages) until the new one resolves; the guard then
    // only fires on true initial load / error.
    placeholderData: keepPreviousData,
  });

  if (isError || !data) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-center text-sm">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="relative h-full overflow-y-auto p-4">
      {data.render_error && (
        <div className="bg-destructive/10 text-destructive mb-3 flex items-start gap-2 rounded-md px-3 py-2 text-xs">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Preview is stale: the last PDF render failed. Fix the content or template and save again.
          </span>
        </div>
      )}
      {Array.from({ length: data.page_count }, (_, i) => (
        // Raw <img>: these are server-rendered PNGs served through our API
        // proxy with a dynamic page count; next/image's loader/optimizer adds
        // no value here and would need domain/loader config for API routes.
        // Cache-bust on the server's render timestamp so the image URL always
        // changes when the PDF re-renders — a caller-supplied counter (studio
        // pdfNonce) resets to 0 on reload and would collide with a stale cache.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={i}
          src={apiUrlForBrowserPdf(
            `${basePath}/preview/page/${i + 1}?v=${encodeURIComponent(
              data.rendered_at ?? String(version ?? ""),
            )}`,
          )}
          alt={`Page ${i + 1}`}
          className="mx-auto mb-4 w-full max-w-3xl rounded-sm bg-white shadow-md"
        />
      ))}
      <span
        className={`bg-foreground text-background sticky bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center rounded-full px-3 py-1 text-xs font-medium shadow ${
          data.page_count > 1 ? "bg-amber-600" : ""
        }`}
      >
        {data.page_count} page{data.page_count > 1 ? "s" : ""}
      </span>
    </div>
  );
}
