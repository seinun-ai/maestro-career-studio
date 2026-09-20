import { toast } from "sonner";

/**
 * Any response that follows a render. Endpoints that render carry the note;
 * the field is optional because a few of them (the `/edits` pair, which
 * targets a base resume or an application) answer with either shape.
 */
export interface RenderNoted {
  render_note?: string | null;
}

/**
 * Surface the backend's explanation of a render fallback, once, when there is
 * one. Non-null only when TeX is absent on the host and a LaTeX template
 * rendered through a Typst one instead — the render SUCCEEDED, so this is an
 * info toast beside the usual success, never in place of it.
 */
export function notifyRenderNote(data: RenderNoted): void {
  if (data.render_note) toast.info(data.render_note);
}
