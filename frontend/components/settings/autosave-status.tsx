"use client";

import { useLayoutEffect, useRef } from "react";
import { Check, Loader2, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { focusIfDropped } from "@/hooks/use-focus-return";

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
 * Three states: Saving…, Not saved (a failed write, with Try again where the
 * card still holds a value the server lacks), and Saves automatically.
 */
export function AutosaveStatus({
  pending,
  failed = false,
  onRetry,
  className,
}: {
  pending: boolean;
  failed?: boolean;
  onRetry?: () => void;
  className?: string;
}) {
  const statusRef = useRef<HTMLSpanElement>(null);
  const refocus = useRef(false);
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
    <span className={`inline-flex min-w-36 items-center justify-end gap-2 text-xs ${className ?? ""}`}>
      <span
        ref={statusRef}
        tabIndex={-1}
        aria-live="polite"
        className={`inline-flex items-center gap-1.5 ${
          failed && !pending ? "text-destructive" : "text-muted-foreground"
        }`}
      >
        {pending ? (
          <>
            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
            Saving…
          </>
        ) : !failed ? (
          <>
            <Check className="size-3" aria-hidden="true" />
            Saves automatically
          </>
        ) : (
          <>
            <TriangleAlert className="size-3" aria-hidden="true" />
            Not saved
          </>
        )}
      </span>
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
