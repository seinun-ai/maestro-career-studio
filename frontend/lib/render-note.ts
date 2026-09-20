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
