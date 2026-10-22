import assert from "node:assert/strict";
import { test } from "node:test";

import { convert, formatPay, midpoint, payLine, periodWords, toYearly } from "./money.ts";

/** CLDR 48 (Node 26) writes en-GB compact amounts in lower case ("€75k"); older CLDR wrote "€75K". The
 * symbols stay pinned exactly ("US$", "CA$", "£"); only a compact suffix right after a digit is compared
 * without case, so the suite holds on every runtime. */
const compact = (s: string | null | undefined) =>
  s == null ? s : s.replace(/(\d)([kmb])(?![a-z])/gi, (_m, d: string, u: string) => d + u.toUpperCase());

test("same currency reads plain, converted reads with ≈ and keeps the posted amount", () => {
  const rates = { base: "EUR", date: "2026-10-19", rates: { GBP: 0.877 } };
  const same = formatPay({ min: 75000, max: 90000, currency: "EUR", period: "year" }, { home: "EUR", rates, locale: "en-GB" });
  assert.equal(compact(same.primary), "€75K–€90K");
  assert.equal(same.posted, null);
  const conv = formatPay({ min: 70000, max: 85000, currency: "GBP", period: "year" }, { home: "EUR", rates, locale: "en-GB" });
  assert.match(compact(conv.primary)!, /^≈ €80K–€97K$/);
  assert.equal(compact(conv.posted), "£70K–£85K");
});

test("no rate shows the posted amount and says so; no pay stays empty", () => {
  const out = formatPay({ min: 2400000, max: null, currency: "ARS", period: "month" }, { home: "EUR", rates: null, locale: "en-GB" });
  assert.equal(out.converted, false);
  assert.equal(formatPay({ min: null, max: null, currency: null, period: null }, { home: "EUR", rates: null, locale: "en-GB" }), null);
});

test("a figure with no rate is shown as posted, one significant decimal kept", () => {
  const out = formatPay({ min: 2400000, max: null, currency: "ARS", period: "month" }, { home: "EUR", rates: null, locale: "en-GB" })!;
  assert.equal(compact(out.primary), "ARS\u00a02.4M"); // Intl joins a code and its number with a no-break space
  assert.equal(out.posted, null);
  assert.equal(out.noRate, true);
  assert.equal(out.period, "month");
  assert.equal(out.rateDate, null);
});

test("another currency shows its own symbol, the home currency its narrow one", () => {
  const rates = { base: "EUR", date: "2026-10-19", rates: { CAD: 1.495, USD: 1.087 } };
  const toronto = formatPay({ min: 120000, max: null, currency: "CAD", period: "year" }, { home: "EUR", rates, locale: "en-GB" })!;
  assert.equal(compact(toronto.posted), "CA$120K"); // an unclear "$" never reads as US dollars
  assert.equal(toronto.converted, true);
  assert.equal(toronto.rateDate, "2026-10-19");
  const home = formatPay({ min: 171000, max: 214000, currency: "USD", period: "year" }, { home: "USD", rates, locale: "en-US" })!;
  assert.equal(compact(home.primary), "$171K–$214K");
});

test("an hourly rate made yearly uses the hours per year and keeps the posted hour", () => {
  const rates = { base: "EUR", date: "2026-10-19", rates: { USD: 1.087 } };
  const out = formatPay(
    { min: 62, max: null, currency: "USD", period: "hour" },
    { home: "EUR", rates, locale: "en-GB", per: "year" },
  )!;
  assert.equal(compact(out.primary), "≈ €119K"); // 62 × 2080 = 128,960 USD
  assert.equal(out.posted, "US$62");
  assert.equal(out.period, "year");
  assert.equal(out.postedPeriod, "hour");
  const fewer = formatPay(
    { min: 62, max: null, currency: "USD", period: "hour" },
    { home: "USD", rates, locale: "en-US", per: "year", hoursPerYear: 1000 },
  )!;
  assert.equal(compact(fewer.primary), "≈ $62K");
});

test("a period it cannot make yearly stays as posted", () => {
  const out = formatPay({ min: 5000, max: null, currency: "EUR", period: null }, { home: "EUR", rates: null, locale: "en-GB", per: "year" })!;
  assert.equal(compact(out.primary), "€5K");
  assert.equal(out.converted, false);
});

test("with no home currency yet, pay reads as posted", () => {
  const out = formatPay({ min: "70000", max: "85000", currency: "gbp", period: "year" }, { locale: "en-GB" })!;
  assert.equal(compact(out.primary), "£70K–£85K");
  assert.equal(out.converted, false);
  assert.equal(out.noRate, false);
});

test("pay with no currency is a plain number, never a guessed dollar", () => {
  const out = formatPay({ min: 75000, max: 90000, currency: null, period: "year" }, { home: "EUR", rates: null, locale: "en-GB" })!;
  assert.equal(compact(out.primary), "75K–90K");
  assert.equal(out.converted, false);
});

test("equal ends read once, and a line carries its period in words", () => {
  const out = formatPay({ min: 80000, max: 80000, currency: "EUR", period: "year" }, { home: "EUR", rates: null, locale: "en-GB" })!;
  assert.equal(compact(out.primary), "€80K");
  assert.equal(compact(payLine(out)), "€80K a year");
  assert.equal(periodWords("hour"), "an hour");
  assert.equal(periodWords("month"), "a month");
  assert.equal(periodWords(null), "");
});

test("the arithmetic mirrors money.py", () => {
  const rates = { base: "EUR", date: "2026-10-19", rates: { USD: 1.087, GBP: 0.877 } };
  assert.equal(convert(100, "EUR", "EUR", rates), 100);
  assert.equal(Math.round(convert(108.7, "USD", "EUR", rates)!), 100);
  assert.equal(convert(1, "ARS", "EUR", rates), null);
  assert.equal(convert(1, "USD", "EUR", null), null);
  assert.equal(convert(50, "usd", "USD", null), 50);
  assert.equal(toYearly(50, "hour"), 104000);
  assert.equal(toYearly(5000, "month"), 60000);
  assert.equal(toYearly(1000, "week"), 52000);
  assert.equal(toYearly(400, "day"), 104000);
  assert.equal(toYearly(1, null), null);
  assert.equal(midpoint(70, 90), 80);
  assert.equal(midpoint(null, 90), 90);
  assert.equal(midpoint(null, null), null);
});
