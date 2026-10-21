/** The motion budget in one place (owner's rule: nothing over 400ms except the Copied hold). */

/** How long a confirmation ("Copied", "Saved") holds before it settles. */
export const CONFIRM_HOLD_MS = 1200;

/** One confirming pulse: globals.css `animate-confirm` runs `--duration-medium4`. */
export const CONFIRM_MS = 400;

/** How long a leaving row takes to collapse: globals.css `.collapse-exit` runs `--duration-short4`. */
export const ROW_EXIT_MS = 200;

/** A number rolling to its new value (NumberRoll): the same `--duration-medium4` as a confirming pulse. */
export const ROLL_MS = 400;

/** A label that cross-fades to a new one (StatusChip): globals.css `animate-status-in`/`-out` run `--duration-short4`. */
export const FADE_MS = 200;
