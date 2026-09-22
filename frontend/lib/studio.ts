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

/**
 * A server JSON value as one comparable string, object keys sorted at every depth. The query
 * cache is structurally shared: a refetch keeps the OLD object, and its key order, for every
 * subtree whose content did not change, while a mutation response is raw. With plain
 * JSON.stringify, a Save that only reordered keys in an untouched section would not match its
 * own refetch (and drafts migrated from Postgres are in JSONB key order).
 */
export function serverKey(value: unknown): string {
  if (value == null) return "";
  return JSON.stringify(value, (_key, v: unknown) =>
    v !== null && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
        )
      : v,
  );
}

export type AdoptAction = "none" | "in-place" | "remount" | "banner";

/**
 * What the tailored studio does when the server's customized_json moves (SYSTEM.md §12).
 * `own`: keys our own Saves returned, oldest first, not yet seen from the server.
 * - a Rebuild the user confirmed → replace the content (remount), even when its key is also
 *   one of ours: the user asked for the server copy;
 * - one of ours → move the baseline IN PLACE (the working copy is never replaced);
 * - anyone else's over a clean editor → replace the content (remount);
 * - anyone else's over unsaved edits → keep the editor; the banner offers Load latest.
 * A queue, not a single "next key is ours" flag: two Saves inside one refetch window would
 * otherwise flash a false banner, and a Save that returns the adopted key arms nothing.
 */
export function adoptServerKey(s: {
  live: string;
  adopted: string;
  own: readonly string[];
  dirty: boolean;
  forced: string | null;
}): { action: AdoptAction; own: string[] } {
  if (s.live === "" || s.live === s.adopted) return { action: "none", own: [...s.own] };
  if (s.live === s.forced) return { action: "remount", own: [] };
  const i = s.own.indexOf(s.live);
  if (i !== -1) return { action: "in-place", own: s.own.slice(i + 1) }; // drops older, unseen own keys too
  if (!s.dirty) return { action: "remount", own: [] };
  return { action: "banner", own: [...s.own] };
}

/** `saved` when `current` still equals what was sent, else `current`: a save's response must not
 *  overwrite an edit made while the save ran. Compared by content ({@link serverKey}): a re-picked
 *  equal value is a new object, and key order is not content. */
export function keepIfEdited<T>(current: T, sent: T, saved: T): T {
  return serverKey(current) === serverKey(sent) ? saved : current;
}

/** Whether typed JSON would change `value`. Whitespace and object key order are not changes; text
 *  that does not parse is (the user would lose it). */
export function jsonDraftDiffers(text: string, value: unknown): boolean {
  try {
    return serverKey(JSON.parse(text)) !== serverKey(value);
  } catch {
    return true;
  }
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

/**
 * A dragged preview width, within the limits. Rounds to 0.1 so the stored value never jumps
 * visibly on release (whole-percent rounding jumped up to 0.5%, about 5px). A non-finite width
 * (a zero-width shell divides by zero) is the default, never a stored NaN.
 */
export function clampPreviewPct(pct: number): number {
  const { min, max } = PREVIEW_PCT;
  if (!Number.isFinite(pct)) return PREVIEW_PCT.default;
  return Math.round(Math.min(max, Math.max(min, pct)) * 10) / 10;
}

/** A stored preview width; the default when absent, garbled or out of range. */
export function parsePreviewPct(raw: string | null): number {
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) && n >= PREVIEW_PCT.min && n <= PREVIEW_PCT.max ? n : PREVIEW_PCT.default;
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
