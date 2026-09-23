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
 * - **A single `pending` flag**, so `AutosaveStatus` reads one boolean, plus
 *   `failed` when the newest value is not on the server and `retry` to send
 *   it again.
 *
 * A rejected commit is `failed`. The caller still reports it through its own
 * `onError`. Each commit sends the whole value, so a later success carries
 * every earlier change and clears `failed`. An outcome with a newer value
 * queued behind it decides nothing. `retry` sends the newest value again.
 *
 * Deliberately does NOT re-seed from a background refetch. There is no
 * non-destructive moment to do it — an autosaving card is almost always either
 * mid-edit or mid-write, and re-seeding in either state overwrites the user.
 * Job preferences, the card this pattern came from, has always worked this way.
 */
export function useAutosave<T>(initial: T, commit: (next: T) => Promise<unknown>) {
  const [value, setValue] = useState(initial);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const queued = useRef(initial);
  const inFlight = useRef<T | null>(null);

  const flush = () => {
    const next = queued.current;
    inFlight.current = next;
    setPending(true);
    // A rejection is reported by the caller's own onError; here it only
    // decides `failed`. The rejection handler keeps it off the unhandled path.
    commit(next).then(
      () => settle(true),
      () => settle(false),
    );
  };

  // `failed`: the newest value is not on the server. A later success carries
  // every earlier change and clears it; an outcome with a newer value queued
  // behind it decides nothing.
  const settle = (ok: boolean) => {
    if (queued.current !== inFlight.current) {
      flush();
      return;
    }
    inFlight.current = null;
    setPending(false);
    setFailed(!ok);
  };

  /** Send the newest value again: the failed state's Try again. */
  const retry = () => {
    if (inFlight.current === null) flush();
  };

  const update = (getNext: (current: T) => T) => {
    const next = getNext(queued.current);
    queued.current = next;
    setValue(next);
    if (inFlight.current === null) flush();
  };

  return { value, update, pending, failed, retry };
}
