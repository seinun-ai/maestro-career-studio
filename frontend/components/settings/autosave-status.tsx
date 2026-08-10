import { Check, Loader2 } from "lucide-react";

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
 * This is an inline, non-interrupting status instead, and it reserves its own
 * width so the row does not reflow as the state changes.
 */
export function AutosaveStatus({
  pending,
  className,
}: {
  pending: boolean;
  className?: string;
}) {
  return (
    <span
      className={`text-muted-foreground inline-flex items-center gap-1.5 text-xs ${className ?? ""}`}
      // polite, not assertive: a save confirmation must never interrupt what a
      // screen-reader user is doing.
      aria-live="polite"
    >
      {pending ? (
        <>
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          Saving…
        </>
      ) : (
        <>
          <Check className="size-3" aria-hidden="true" />
          Saves automatically
        </>
      )}
    </span>
  );
}
