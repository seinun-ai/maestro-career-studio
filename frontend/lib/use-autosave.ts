"use client";

import { useRef, useState } from "react";

/**
 * Autosave with at most one write in flight and only the newest edit queued.
 *
 * Every autosaving settings card needs the same three guarantees, and they had
 * been written out separately in Job preferences and (in a third variant, via
 * `lib/onboarding`) in the persona editor:
 *
 * - **One request at a time.** Typing into a text field would otherwise fire a
 *   PUT per keystroke.
 * - **Last write wins.** While a save is in flight, further edits replace the
 *   queued value rather than stacking; when the response lands, the newest
 *   value goes out. Queueing every intermediate edit would replay a value the
 *   user has already moved past.
 * - **A single `pending` flag**, so `AutosaveStatus` reads one boolean.
 *
 * A rejected commit still drains the queue: the caller reports the failure
 * through its own mutation's `onError`, and the next edit is a fresh attempt
 * carrying the latest value, which is the useful retry.
 *
 * Deliberately does NOT re-seed from a background refetch. There is no
 * non-destructive moment to do it — an autosaving card is almost always either
 * mid-edit or mid-write, and re-seeding in either state overwrites the user.
 * Job preferences, the card this pattern came from, has always worked this way.
 */
export function useAutosave<T>(initial: T, commit: (next: T) => Promise<unknown>) {
  const [value, setValue] = useState(initial);
  const [pending, setPending] = useState(false);
  const queued = useRef(initial);
  const inFlight = useRef<T | null>(null);

  const flush = () => {
    const next = queued.current;
    inFlight.current = next;
    setPending(true);
    void commit(next)
      .catch(() => {
        // Reported by the caller's own onError; swallowed here so a failed
        // save cannot reject into an unhandled promise.
      })
      .finally(() => {
        if (queued.current !== inFlight.current) {
          flush();
        } else {
          inFlight.current = null;
          setPending(false);
        }
      });
  };

  const update = (getNext: (current: T) => T) => {
    const next = getNext(queued.current);
    queued.current = next;
    setValue(next);
    if (inFlight.current === null) flush();
  };

  return { value, update, pending };
}
