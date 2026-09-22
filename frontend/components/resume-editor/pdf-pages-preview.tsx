"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { apiFetch, apiUrlForBrowserPdf } from "@/lib/api";
import {
  actualSizeWidthPx,
  parseZoom,
  PREVIEW_ZOOMS,
  type PreviewZoom,
} from "@/lib/studio";
import { cn } from "@/lib/utils";

type Manifest = {
  page_count: number;
  rendered_at: string | null;
  render_error: string | null;
};

const ZOOM_KEY = "pdfPreview.zoom";

const PAGE_CLASS: Record<PreviewZoom, string> = {
  // The long-standing default: the page fills the pane's width, capped.
  width: "w-full max-w-3xl",
  // Whole page in view. `cqh` is the scroller's own content height (it is a
  // size container), not the viewport's: the job page's Resume tab is an 80vh
  // box, and the studio pane loses height to its header, the stale strip and
  // the formatting panel, so no viewport offset fits every caller.
  page: "max-h-[100cqh] w-auto max-w-full",
  // Print size: width set inline from the PNG's natural width.
  actual: "max-w-none",
};

/**
 * Clean PDF preview: server-rasterized page PNGs on the grey canvas, with zoom
 * presets and a floating page-count pill — replaces the browser's native PDF
 * viewer chrome. The zoom choice is one preference for every preview surface.
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
  const [zoom, setZoom] = useState<PreviewZoom>("width");
  const [naturalWidth, setNaturalWidth] = useState<number | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrating from localStorage after mount
    setZoom(parseZoom(window.localStorage.getItem(ZOOM_KEY)));
  }, []);
  const chooseZoom = (value: PreviewZoom) => {
    setZoom(value);
    window.localStorage.setItem(ZOOM_KEY, value);
  };

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
      <div className="bg-canvas text-muted-foreground flex h-full items-center justify-center p-6 text-center text-sm">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="bg-canvas flex h-full flex-col">
      {/* A row above the scroller, not a sticky child of it: at 100% the page
          scrolls sideways, and a sticky child scrolls away with it. In flow,
          the group wraps in a narrow pane instead of clipping. */}
      <div className="flex shrink-0 justify-end px-4 pt-2">
        <div
          role="group"
          aria-label="Zoom"
          className="bg-background/90 flex flex-wrap justify-end gap-0.5 rounded-md border p-0.5 shadow-sm"
        >
          {PREVIEW_ZOOMS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={zoom === option.value}
              onClick={() => chooseZoom(option.value)}
              className={cn(
                "h-6 rounded px-2 text-xs transition-colors",
                zoom === option.value
                  ? "bg-secondary-container text-on-secondary-container font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      {/* overflow-auto: 100% scrolls sideways. A size container, so "Fit
          page" can measure the room it has. */}
      <div className="min-h-0 flex-1 overflow-auto px-4 pt-2 pb-4 @container-[size]">
        {data.render_error && (
          <div className="bg-destructive/10 text-destructive mb-3 flex items-start gap-2 rounded-md px-3 py-2 text-xs">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>
              Preview is stale: the last PDF render failed. Fix the content or template, then save or regenerate the PDF.
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
            onLoad={
              i === 0
                ? (e) => setNaturalWidth(e.currentTarget.naturalWidth)
                : undefined
            }
            style={
              zoom === "actual" && naturalWidth
                ? { width: actualSizeWidthPx(naturalWidth) }
                : undefined
            }
            className={cn(
              "mx-auto mb-4 block rounded-[2px] bg-white shadow-lg ring-1 ring-black/5",
              PAGE_CLASS[zoom],
            )}
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
    </div>
  );
}
