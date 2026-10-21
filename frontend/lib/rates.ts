/**
 * How a share reads (owner decision D7), the web half of `backend/app/services/rates.py`. Pure so `node --test`
 * loads it: it imports only types. From MIN_RATE_N in the denominator a share is a percent with its Wilson 95%
 * range, the likely true rate; below it, the counts ("5 of 12"). The server already leaves the rate out below
 * 20; this file holds the same line, so a rate never shows on fewer.
 */
import type { RateCount } from "./types";

/** `services/rates.py` MIN_RATE_N. */
export const MIN_RATE_N = 20;

export interface RateWords {
  /** "19%", or "5 of 12" below MIN_RATE_N, or "—" when there is nothing to count. */
  value: string;
  /** "11–30%", the likely range; null with no rate. */
  range: string | null;
}

const percent = (share: number) => Math.round(share * 100);

/** The share reads as a percent: the server sent a rate and there are at least MIN_RATE_N in its denominator. */
export function showsRate(r: RateCount): boolean {
  return r.rate !== null && r.of >= MIN_RATE_N;
}

/** A share in words. `unit` is its denominator's noun, one and many ("reply", "replies"). */
export function rateWords(r: RateCount, unit?: readonly [string, string]): RateWords {
  if (r.of === 0) return { value: "—", range: null };
  if (!showsRate(r) || r.rate === null) {
    const noun = unit ? ` ${r.of === 1 ? unit[0] : unit[1]}` : "";
    return { value: `${r.count} of ${r.of}${noun}`, range: null };
  }
  const range = r.low !== null && r.high !== null ? `${percent(r.low)}–${percent(r.high)}%` : null;
  return { value: `${percent(r.rate)}%`, range };
}
