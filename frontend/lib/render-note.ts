import { toast } from "sonner";

import type { RenderNoted } from "@/lib/types";

/** One slot for the note: see `notifyRenderNote`. */
const RENDER_NOTE_TOAST_ID = "render-note";

/**
 * Surface the backend's explanation of a render fallback, when there is one.
 * The render SUCCEEDED, under another engine, so this is an info toast beside
 * the usual success, never in place of it.
 *
 * It fires on EVERY substituted render by design, ungated: the gallery badge
 * and the setup checklist row are the persistent explanation, this is the
 * per-action one. The note is one fixed string, so all of them share a toast
 * id — a save that chains render and re-score, or a run of one-at-a-time
 * applies, updates the single note in place instead of minting copies that
 * push the other toasts out of sonner's three-slot default.
 *
 * Takes `undefined` because `apiFetch` resolves to it on a 204.
 */
export function notifyRenderNote(data: RenderNoted | undefined): void {
  if (data?.render_note) {
    toast.info(data.render_note, { id: RENDER_NOTE_TOAST_ID });
  }
}

/**
 * A payload from a route that renders AFTER it commits: it carries the note
 * when another engine stood in, and `render_error` when the render failed
 * outright. The two are alternatives, never both.
 */
type RenderOutcome = RenderNoted & { render_error?: string | null };

/**
 * Both halves of the post-commit render contract, for the callers that face
 * both: the note (unchanged, same single toast slot), then — when the render
 * failed — one warning naming what is still holding its previous PDF.
 *
 * The warning is a `toast.warning` BESIDE the caller's own `toast.success`,
 * not instead of it: the write landed, only the PDF is stale. It carries no
 * shared id, because `staleLabel` makes each one a different sentence.
 *
 * `staleLabel` is the subject of that sentence — the resume whose PDF is now
 * behind, e.g. a base-resume display name, or "The resume" where only one is
 * in play. Sentence case, no trailing period; the helper supplies the rest.
 */
export function notifyRenderOutcome(
  data: RenderOutcome | undefined,
  { staleLabel }: { staleLabel: string },
): void {
  notifyRenderNote(data);
  if (data?.render_error) {
    toast.warning(`${staleLabel} kept its previous PDF: the re-render failed.`);
  }
}
