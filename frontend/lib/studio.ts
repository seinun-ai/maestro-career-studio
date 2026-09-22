/**
 * Pure helpers for the resume studios. No DOM, no React: `node --test` runs
 * them directly (lib/studio.test.ts).
 */

export type SaveStatusInput = {
  dirty: boolean;
  saving: boolean;
  rendering: boolean;
  rescoring: boolean;
};

export type SaveStatus = { label: string; tone: "busy" | "dirty" | "clean" };

/**
 * The studio's one save-status line. Work in flight outranks everything (a
 * Save is still "dirty" until the server copy is adopted), then unsaved
 * edits, then clean. It sits beside the title, where Google Docs and
 * Reactive Resume both put it.
 */
export function saveStatus(s: SaveStatusInput): SaveStatus {
  if (s.saving) return { label: "Saving…", tone: "busy" };
  if (s.rendering) return { label: "Rendering PDF…", tone: "busy" };
  if (s.rescoring) return { label: "Re-scoring…", tone: "busy" };
  if (s.dirty) return { label: "Unsaved changes", tone: "dirty" };
  return { label: "All changes saved", tone: "clean" };
}

/** Width of the preview pane, as a percent of the studio. */
export const PREVIEW_PCT = { default: 45, min: 25, max: 70, step: 5 } as const;

/**
 * Keyboard move for the editor/preview divider (APG window-splitter
 * pattern). The divider's value is the EDITOR's share, so Left moves it left:
 * a smaller editor, a wider preview. Home/End jump to the limits; any other
 * key returns null so the caller leaves the event alone.
 */
export function nextPreviewPct(pct: number, key: string): number | null {
  const { min, max, step } = PREVIEW_PCT;
  switch (key) {
    case "ArrowLeft":
      return Math.min(max, pct + step);
    case "ArrowRight":
      return Math.max(min, pct - step);
    case "Home":
      return max;
    case "End":
      return min;
    default:
      return null;
  }
}

export type PreviewZoom = "width" | "page" | "actual";

export const PREVIEW_ZOOMS: { value: PreviewZoom; label: string }[] = [
  { value: "width", label: "Fit width" },
  { value: "page", label: "Fit page" },
  { value: "actual", label: "100%" },
];

export function parseZoom(value: string | null): PreviewZoom {
  return value === "page" || value === "actual" ? value : "width";
}

/**
 * The DPI the backend rasterizes preview pages at (`app/services/pdf_preview.DPI`).
 * Pinned equal by backend/tests/test_frontend_studio.py: a cross-boundary
 * constant needs a contract test, not a comment.
 */
export const PREVIEW_DPI = 150;

/** CSS width for true print size (a CSS inch is 96px). */
export function actualSizeWidthPx(naturalWidthPx: number): number {
  return Math.round((naturalWidthPx * 96) / PREVIEW_DPI);
}
