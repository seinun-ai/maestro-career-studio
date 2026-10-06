const KEY = "cs-inbox-last-visit";
const DAY_MS = 24 * 60 * 60 * 1000;

type VisitStorage = Pick<Storage, "getItem" | "setItem">;

/** Reads one tab's previous visit and remembers it until this clock is discarded. */
export function createVisitClock() {
  let cachedSince: string | null = null;
  return {
    resolve(storage: VisitStorage | null, nowMs: number): string {
      if (cachedSince !== null) return cachedSince;

      let stored: string | null = null;
      if (storage) {
        try {
          stored = storage.getItem(KEY);
        } catch {
          // A blocked read uses the same last-day fallback as missing storage.
        }
      }
      const valid = stored && !Number.isNaN(Date.parse(stored)) ? stored : null;
      cachedSince = valid ?? new Date(nowMs - DAY_MS).toISOString();
      if (storage) {
        try {
          storage.setItem(KEY, new Date(nowMs).toISOString());
        } catch {
          // Remembering a visit is optional; the dashboard still works.
        }
      }
      return cachedSince;
    },
  };
}
