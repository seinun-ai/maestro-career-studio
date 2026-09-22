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
 * The studio's one save-status line. A Save in flight outranks everything (the
 * editor is still "dirty" until the server copy is adopted). Unsaved edits
 * come next, ahead of the render and re-score that follow a save: an edit
 * typed while the PDF renders is not in that PDF, so the line must not read
 * as if the work is on its way. Then the render, the re-score, and clean. It
 * renders in the header subtitle, directly below the title (after the job
 * label in the tailored studio).
 */
export function saveStatus(s: SaveStatusInput): SaveStatus {
  if (s.saving) return { label: "Saving…", tone: "busy" };
  if (s.dirty) return { label: "Unsaved changes", tone: "dirty" };
  if (s.rendering) return { label: "Rendering PDF…", tone: "busy" };
  if (s.rescoring) return { label: "Re-scoring…", tone: "busy" };
  return { label: "All changes saved", tone: "clean" };
}

/**
 * What an empty studio preview says: the action that is enabled right now.
 * Save is dirty-gated, so a clean studio with no PDF (just after Build draft
 * or Rebuild from base) cannot save, and ⋯ Generate PDF is disabled while
 * edits are unsaved. "More resume actions" is the ⋯ trigger's accessible name.
 */
export function emptyPreviewMessage(unsaved: boolean): string {
  return unsaved
    ? "No PDF yet. Save to render one."
    : "No PDF yet. Generate one from More resume actions (⋯).";
}

/** Width of the preview pane, as a percent of the studio. */
export const PREVIEW_PCT = { default: 45, min: 25, max: 70, step: 5 } as const;

/**
 * Keyboard move for the editor/preview divider (APG window-splitter
 * pattern). The divider's value is the EDITOR's share, so Left moves it left:
 * a smaller editor, a wider preview. Arrows land on the step grid, because a
 * pointer drag leaves a fractional width (47.38 steps to 50 or 45, never
 * 52.38). Home/End jump to the limits; any other key returns null so the
 * caller leaves the event alone.
 */
export function nextPreviewPct(pct: number, key: string): number | null {
  const { min, max, step } = PREVIEW_PCT;
  switch (key) {
    case "ArrowLeft":
      return Math.min(max, Math.floor(pct / step) * step + step);
    case "ArrowRight":
      return Math.max(min, Math.ceil(pct / step) * step - step);
    case "Home":
      return max;
    case "End":
      return min;
    default:
      return null;
  }
}

export type PreviewZoom = "width" | "page" | "actual";

export const PREVIEW_ZOOMS: ReadonlyArray<{ value: PreviewZoom; label: string }> = [
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
