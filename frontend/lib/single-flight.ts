/** The lock behind `useSingleFlight` (`hooks/use-single-flight.ts`). No React, so `node --test` runs it. */

type Mutate<TVars> = (vars: TVars, options?: { onSettled?: () => void }) => void;

/**
 * Starts `mutate(vars)` unless a request `lock` started is still running. The lock shuts before the request
 * starts and opens only when that request settles (success or error), never sooner.
 */
export function startOnce<TVars>(lock: { current: boolean }, mutate: Mutate<TVars>, vars: TVars): void {
  if (lock.current) return;
  lock.current = true;
  mutate(vars, {
    onSettled: () => {
      lock.current = false;
    },
  });
}
