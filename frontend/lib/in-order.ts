const tails = new Map<string, Promise<unknown>>();

/**
 * Runs `run` after every earlier call with the same `key` has settled, so requests that must not overtake each
 * other (saves to one record) reach the server in the order they were made. A failed earlier call does not stop
 * the next one. It never waits on anything but those calls: not on tab focus, not on the network state, which a
 * queued TanStack mutation scope does. Calls with different keys do not wait on each other.
 */
export function inOrder<T>(key: string, run: () => Promise<T>): Promise<T> {
  const previous = tails.get(key) ?? Promise.resolve();
  const result = previous.catch(() => {}).then(run);
  const tail = result.catch(() => {});
  tails.set(key, tail);
  // Drop the entry once this call settles, unless a later call has already taken its place.
  void tail.then(() => {
    if (tails.get(key) === tail) tails.delete(key);
  });
  return result;
}
