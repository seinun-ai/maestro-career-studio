"use client";

import { useState } from "react";
import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The page-1 preview image a gallery card leads with.
 *
 * Owns the two behaviours that are easy to get wrong, and that were previously
 * written out once per gallery:
 *
 * 1. **"Nothing to show yet" and "the image broke" must not look the same.**
 *    Pass `src={null}` for the former and get the placeholder; a broken image
 *    falls back to the SAME placeholder rather than a broken-image box.
 * 2. **A healthy-looking row does not guarantee the image exists.** Rasterized
 *    pages are untracked runtime output, so a wiped volume or a fresh clone
 *    against an existing database leaves rows whose image 404s. We remember the
 *    failed SRC rather than a bare boolean, so re-rendering — which changes the
 *    caller's cache-busting query — retries automatically.
 *
 * Callers own the URL (including its `?v=` cache-buster) and the vocabulary:
 * what "not ready" is called, and whether a degraded-but-showable state earns a
 * corner chip.
 */
export function PreviewThumbnail({
  src,
  alt,
  placeholder,
  chip,
  className,
}: {
  /** `null` when there is no preview to show — renders `placeholder` instead. */
  src: string | null;
  alt: string;
  /** Shown when there is no image, e.g. "Not validated" / "Not rendered yet". */
  placeholder: string;
  /** Corner marker for a state that is degraded but still worth showing. */
  chip?: { label: string; title?: string; className?: string };
  className?: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const showImage = src !== null && failedSrc !== src;

  return (
    <div
      className={cn(
        // Full-bleed inside the card: round only the TOP corners to match the
        // card's radius, and keep a single bottom rule as the separator from
        // the card body. A full box border here would double up with the
        // card's own ring along the left, right and top edges.
        "bg-muted/40 relative aspect-[17/22] w-full overflow-hidden rounded-t-xl border-b",
        className,
      )}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt}
          loading="lazy"
          onError={() => setFailedSrc(src)}
          className="h-full w-full bg-white object-cover object-top"
        />
      ) : (
        <div className="text-muted-foreground flex h-full w-full flex-col items-center justify-center gap-2 text-xs">
          <FileText className="size-6 opacity-40" aria-hidden />
          {placeholder}
        </div>
      )}
      {showImage && chip && (
        <span
          className={cn(
            "bg-background/90 text-muted-foreground absolute bottom-1.5 left-1.5 rounded px-1.5 py-0.5 text-[10px] backdrop-blur",
            chip.className,
          )}
          title={chip.title}
        >
          {chip.label}
        </span>
      )}
    </div>
  );
}
