/** The motion budget in one place (owner's rule: nothing over 400ms except the Copied hold). */

/** How long a confirmation ("Copied", "Saved") holds before it settles. */
export const CONFIRM_HOLD_MS = 1200;

/** One confirming pulse: globals.css `animate-confirm` runs `--duration-medium4`. */
export const CONFIRM_MS = 400;

/** How long a leaving row takes to collapse: globals.css `.collapse-exit` runs `--duration-short4`. */
export const ROW_EXIT_MS = 200;
