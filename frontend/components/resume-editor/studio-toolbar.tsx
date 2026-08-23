import type { ReactNode } from "react";

/**
 * The resume studio's option bar, as an ordered set of slots.
 *
 * Both studios were assembled by hand in the order their features happened to
 * be added, so the same actions sat in different positions in each. The base
 * studio additionally led with its RAREST action (Import from Career KB,
 * disabled whenever there are unsaved edits) and had no overflow at all, while
 * the tailored studio had one.
 *
 * There is no view slot. The form ⇄ raw JSON toggle used to lead the bar in
 * both studios; it now lives in `overflow` as "Edit raw JSON" — the raw view
 * carries its own Cancel back to the form, so leaving it never needed a bar
 * button — and History sits beside it there in both. Neither is used more than
 * once a session — the rule below — and the bar's space is better spent on the
 * actions that are.
 *
 * `status` is base-only now: a tailored resume's health score is inherited from
 * its base, so the tailored studio checks structure through the post-tailoring
 * review instead and leaves this slot empty.
 *
 * Slots exist rather than a `children` array so the order is a property of this
 * file and not of each call site. Reading left to right the bar answers, in
 * order: is it healthy → what can I do to it → the one thing I probably came
 * here to do → everything rare.
 *
 * Rules that go with it:
 * - `primary` is the ONLY filled button in the bar. A toggle that is "on"
 *   (Review changes) uses the `tonal` variant, never `default`, or the view has
 *   two competing filled buttons.
 * - `overflow` holds the rare and the destructive. If an action is used once a
 *   session or cannot be undone, it belongs there, not inline.
 * - `status` may be interactive, but only in ways that cannot change the
 *   document — navigate to a report, open a detail surface, retry its own
 *   fetch. Any mutation lives behind that intermediate surface (the KB sync
 *   pill's Sync button), never on the bar itself.
 * - A transient message ("Save your edits first") is not a toolbar item at all
 *   — it belongs on the disabled control's tooltip, where it is read at the
 *   moment it applies.
 */
export function StudioToolbar({
  status,
  tools,
  primary,
  overflow,
}: {
  /** Health badges and sync pills — see the `status` rule above. */
  status?: ReactNode;
  /** Document tools: template, re-score, review. */
  tools?: ReactNode;
  /** The one filled button. */
  primary?: ReactNode;
  /** Rare and destructive, behind a ⋯ menu. */
  overflow?: ReactNode;
}) {
  return (
    <>
      {status}
      {tools}
      {primary}
      {overflow}
    </>
  );
}
