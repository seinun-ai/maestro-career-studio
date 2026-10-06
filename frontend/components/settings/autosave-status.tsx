"use client";

import { useLayoutEffect, useRef } from "react";
import { CircleCheck, Loader2, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { focusIfDropped } from "@/hooks/use-focus-return";
import { useSavedHold } from "@/hooks/use-saved-hold";

/**
 * The quiet half of the settings save model.
 *
 * The owner's rule: pure preferences autosave, anything with a cost or a blast
 * radius keeps an explicit Save. That only works if a user can TELL which kind
 * of card they are looking at — otherwise "no Save button" reads as "I haven't
 * saved yet" rather than "there is nothing to press".
 *
 * A toast is the wrong instrument here. A toast is for something you should
 * notice; an autosave is the opposite, and Job preferences proved it — its
 * writes coalesce one-in-flight-at-a-time, so typing a location fired several
 * PUTs and stacked several "Job preferences saved" toasts for a single edit.
 * This is an inline, non-interrupting status instead. It sits in the card
 * header beside the title (`SettingCardAction`), whose auto column takes its
 * width from this span, so `min-w-36` holds the widest state's width ("Not
 * saved Try again", about 126px) and the description does not re-wrap as the
 * state changes.
 *
 * Four states: Saving…, Saved (a success says so for a moment, then settles),
 * Not saved (a failed write, with Try again where the card still holds a value
 * the server lacks), and Saves automatically (words only, outside the live
 * region; `idle={false}` drops it while the card holds an unsaved value).
 */

export function AutosaveStatus({
  pending,
  failed = false,
  idle = true,
  onRetry,
  className,
}: {
  pending: boolean;
  failed?: boolean;
  /** False while the card holds an unsaved value (a typed key): "Saves automatically" would be untrue. */
  idle?: boolean;
  onRetry?: () => void;
  className?: string;
}) {
  const statusRef = useRef<HTMLSpanElement>(null);
  const refocus = useRef(false);
  const justSaved = useSavedHold(pending, failed);
  // Try again stays mounted while the retry runs (`failed` holds until a
  // success settles). Once the retry settles: a success unmounts it, and the
  // focus it dropped goes to the status. A failure leaves it, and focus, in
  // place and disarms, so a later ordinary save never pulls focus mid-typing.
  // A layout effect, so no frame is painted with focus on <body>.
  useLayoutEffect(() => {
    if (!refocus.current || pending) return;
    refocus.current = false;
    if (!failed) focusIfDropped(statusRef.current);
  }, [failed, pending]);
  return (
    <span className={`inline-flex min-w-36 items-center justify-end gap-2 text-body-small ${className ?? ""}`}>
      <span
        ref={statusRef}
        tabIndex={-1}
        aria-live="polite"
        className={`inline-flex items-center gap-1.5 ${
          failed && !pending ? "text-destructive" : justSaved ? "text-success" : "text-muted-foreground"
        }`}
      >
        {pending ? (
          <>
            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
            Saving…
          </>
        ) : !failed && justSaved ? (
          <>
            <CircleCheck className="size-3 animate-confirm rounded-full" aria-hidden="true" />
            Saved
          </>
        ) : !failed ? null : (
          <>
            <TriangleAlert className="size-3" aria-hidden="true" />
            Not saved
          </>
        )}
      </span>
      {/* Outside the live region: each autosave announces Saving… then Saved, and stops. */}
      {!pending && !failed && !justSaved && idle ? (
        <span className="text-muted-foreground">Saves automatically</span>
      ) : null}
      {failed && onRetry ? (
        <Button
          type="button"
          variant="link"
          size="xs"
          focusableWhenDisabled
          disabled={pending}
          className="h-auto p-0 data-disabled:opacity-50"
          onClick={() => {
            refocus.current = true;
            onRetry();
          }}
        >
          Try again
        </Button>
      ) : null}
    </span>
  );
}
