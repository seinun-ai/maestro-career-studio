import type { ReactNode } from "react";

/**
 * The resume studio's option bar, as an ordered set of slots.
 *
 * Both studios carry the same three controls — the view toggle, the health
 * status, and History — and before this they appeared in three different
 * positions each, because each toolbar was assembled by hand in the order its
 * features happened to be added. The base studio additionally led with its
 * RAREST action (Import from Career KB, disabled whenever there are unsaved
 * edits) and had no overflow at all, while the tailored studio had one.
 *
 * Slots exist rather than a `children` array so the order is a property of this
 * file and not of each call site. Reading left to right the bar answers, in
 * order: what am I looking at → is it healthy → what can I do to it → the one
 * thing I probably came here to do → everything rare.
 *
 * Rules that go with it:
 * - `primary` is the ONLY filled button in the bar. A toggle that is "on"
 *   (Review changes) uses the `tonal` variant, never `default`, or the view has
 *   two competing filled buttons.
 * - `overflow` holds the rare and the destructive. If an action is used once a
 *   session or cannot be undone, it belongs there, not inline.
 * - Status is not an action. Health badges render in `status`; a transient
 *   message ("Save your edits first") is not a toolbar item at all — it belongs
 *   on the disabled control's tooltip, where it is read at the moment it
 *   applies.
 */
export function StudioToolbar({
  view,
  status,
  tools,
  primary,
  overflow,
}: {
  /** Form ⇄ Raw JSON. First, because it changes what everything else means. */
  view?: ReactNode;
  /** Health badges — informational, never an action. */
  status?: ReactNode;
  /** Document tools: History, template, re-score, review. */
  tools?: ReactNode;
  /** The one filled button. */
  primary?: ReactNode;
  /** Rare and destructive, behind a ⋯ menu. */
  overflow?: ReactNode;
}) {
  return (
    <>
      {view}
      {status}
      {tools}
      {primary}
      {overflow}
    </>
  );
}
