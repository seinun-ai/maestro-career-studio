/**
 * One formatter for pay (owner decision D8). It mirrors `backend/app/services/money.py`:
 *
 * - A figure in the home currency reads plain ("€75K–€90K"). A converted one, or one made
 *   yearly from another period, reads with "≈" and keeps the posted amount ("£70K–£85K").
 * - A conversion goes through the euro on the ECB reference rates (`GET /api/fx/rates`). With
 *   no rate for the currency, or no rates yet, the posted amount shows and `noRate` says so:
 *   never a guessed rate.
 * - A range stays a range, missing pay stays missing (null), and no currency is ever assumed.
 *
 * The home currency shows its narrow symbol; every other currency its full symbol, so an unclear
 * "$" reads "US$" or "CA$".
 */

/** How a posting states its pay (`jobs.salary_period`). */
export type PayPeriod = "hour" | "day" | "week" | "month" | "year";
/** How the user wants pay shown (the money setting's `period`). */
export type ShowPer = "year" | "month" | "hour";

/** ECB reference rates, units per one `base` (the euro). */
export interface FxRates {
  base: string;
  date: string;
  rates: Record<string, number>;
}

export interface Pay {
  min: number | string | null | undefined;
  max: number | string | null | undefined;
  currency: string | null | undefined;
  period: string | null | undefined;
}

export interface PayOptions {
  /** ISO 4217 code pay is shown in; absent, pay reads as posted. */
  home?: string | null;
  rates?: FxRates | null;
  locale?: string;
  /** Show pay per this period; absent, as posted. */
  per?: ShowPer;
  hoursPerYear?: number;
}

export interface FormattedPay {
  /** "€75K–€90K", or "≈ €80K–€97K" when converted. */
  primary: string;
  /** The posted amount, set only when `primary` is converted. */
  posted: string | null;
  /** `primary` differs from the posting (another currency or another period). */
  converted: boolean;
  /** The posting's currency has no rate (or there are no rates yet): shown as posted. */
  noRate: boolean;
  /** The period `primary` is in. */
  period: string | null;
  /** The period the posting stated. */
  postedPeriod: string | null;
  /** The ECB rate date, when a rate was used. */
  rateDate: string | null;
}

export const HOURS_PER_YEAR = 2080;
/** Marks every figure that is not as posted (converted, or made yearly). */
export const APPROX = "≈ ";
const PER_YEAR: Record<string, number> = { day: 260, week: 52, month: 12, year: 1 };
const PERIOD_WORDS: Record<string, string> = {
  hour: "an hour",
  day: "a day",
  week: "a week",
  month: "a month",
  year: "a year",
};

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

function perBase(code: string, rates: FxRates): number | null {
  if (code === (rates.base || "EUR").toUpperCase()) return 1;
  const rate = rates.rates[code];
  return typeof rate === "number" && Number.isFinite(rate) && rate > 0 ? rate : null;
}

/** `amount` in `from`, expressed in `to`; null when it cannot be known. */
export function convert(
  amount: number | null,
  from: string | null | undefined,
  to: string | null | undefined,
  rates: FxRates | null | undefined,
): number | null {
  if (amount === null || !from || !to) return null;
  const source = from.toUpperCase();
  const target = to.toUpperCase();
  if (source === target) return amount;
  if (!rates) return null;
  const a = perBase(source, rates);
  const b = perBase(target, rates);
  return a === null || b === null ? null : (amount / a) * b;
}

/** A per-period amount as a yearly one; null for no amount or a period it does not know. */
export function toYearly(
  amount: number | null,
  period: string | null | undefined,
  hoursPerYear: number = HOURS_PER_YEAR,
): number | null {
  if (amount === null || !period) return null;
  if (period === "hour") return amount * hoursPerYear;
  const factor = PER_YEAR[period];
  return factor === undefined ? null : amount * factor;
}

function fromYearly(amount: number, per: ShowPer, hoursPerYear: number): number {
  return per === "hour" ? amount / hoursPerYear : amount / PER_YEAR[per];
}

/** The middle of a range, or the one end given. */
export function midpoint(low: number | null, high: number | null): number | null {
  if (low === null) return high;
  if (high === null) return low;
  return (low + high) / 2;
}

/** "a year", "an hour"; empty for no period. */
export function periodWords(period: string | null | undefined): string {
  return period ? (PERIOD_WORDS[period] ?? "") : "";
}

/** A figure with its period in words: "≈ €80K–€97K a year". */
export function payLine(pay: FormattedPay): string {
  const words = periodWords(pay.period);
  return words ? `${pay.primary} ${words}` : pay.primary;
}

function formatAmount(amount: number, code: string | null, home: string | null, locale?: string): string {
  // Compact, whole units, but one decimal where it carries meaning ("2.4M", not "2M").
  const shape = {
    notation: "compact",
    maximumFractionDigits: 0,
    maximumSignificantDigits: 2,
    roundingPriority: "morePrecision",
  } as const;
  if (!code) return new Intl.NumberFormat(locale, shape).format(amount);
  try {
    return new Intl.NumberFormat(locale, {
      ...shape,
      style: "currency",
      currency: code,
      currencyDisplay: code === home ? "narrowSymbol" : "symbol",
    }).format(amount);
  } catch {
    // A code Intl does not know still shows, as written.
    return `${code} ${new Intl.NumberFormat(locale, shape).format(amount)}`;
  }
}

/**
 * Both ends, each with its symbol, joined by "–". `Intl.NumberFormat#formatRange` is not used:
 * it collapses the shared symbol and unit ("€75–90K", which reads as €75 to €90K) and writes
 * equal ends as "~€80K", a second approximation sign beside ours.
 */
function formatRange(low: number | null, high: number | null, code: string | null, home: string | null, locale?: string): string {
  const lo = low === null ? null : formatAmount(low, code, home, locale);
  const hi = high === null ? null : formatAmount(high, code, home, locale);
  if (lo && hi && lo !== hi) return `${lo}–${hi}`;
  return (lo ?? hi) as string;
}

/** Pay as it should read for this user; null when the posting states none. */
export function formatPay(pay: Pay, options: PayOptions = {}): FormattedPay | null {
  const low = toNumber(pay.min);
  const high = toNumber(pay.max);
  if (low === null && high === null) return null;
  const code = pay.currency ? pay.currency.toUpperCase() : null;
  const home = options.home ? options.home.toUpperCase() : null;
  const postedPeriod = pay.period ?? null;
  const hours = options.hoursPerYear && options.hoursPerYear > 0 ? options.hoursPerYear : HOURS_PER_YEAR;
  const posted = formatRange(low, high, code, home, options.locale);
  const asPosted = (noRate: boolean): FormattedPay => ({
    primary: posted,
    posted: null,
    converted: false,
    noRate,
    period: postedPeriod,
    postedPeriod,
    rateDate: null,
  });

  const target = home && code ? home : code;
  const reperiod = Boolean(options.per && postedPeriod && options.per !== postedPeriod && toYearly(1, postedPeriod) !== null);
  const recurrency = Boolean(code && home && code !== home);
  if (!reperiod && !recurrency) return asPosted(false);

  const shift = (value: number | null): number | null => {
    if (value === null) return null;
    let out: number | null = value;
    if (recurrency) out = convert(out, code, target, options.rates);
    if (out !== null && reperiod && options.per) {
      const yearly = toYearly(out, postedPeriod, hours);
      out = yearly === null ? null : fromYearly(yearly, options.per, hours);
    }
    return out;
  };
  const newLow = shift(low);
  const newHigh = shift(high);
  if ((low !== null && newLow === null) || (high !== null && newHigh === null)) {
    return asPosted(recurrency);
  }
  return {
    primary: APPROX + formatRange(newLow, newHigh, target, home, options.locale),
    posted,
    converted: true,
    noRate: false,
    period: reperiod ? (options.per ?? null) : postedPeriod,
    postedPeriod,
    rateDate: recurrency ? (options.rates?.date ?? null) : null,
  };
}
