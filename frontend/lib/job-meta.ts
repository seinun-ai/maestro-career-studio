/**
 * A job's one-line facts ("Acme · Austin, TX · Hybrid"): empty parts and "Not stated" drop out, and a
 * part that repeats one before it ("Remote · Remote", location and work mode both) shows once. The job
 * header and the Agent inbox row both read it. No imports: `node --test` loads this file as it is.
 */
export function jobMetaLine(parts: readonly (string | null | undefined)[]): string {
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const raw of parts) {
    const part = raw?.trim();
    if (!part || part === "Not stated") continue;
    const key = part.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    kept.push(part);
  }
  return kept.join(" · ");
}

/** A currency's plural name in words ("Canadian dollars", "euros"); a code Intl does not know, as written. */
function currencyWords(code: string): string {
  try {
    const parts = new Intl.NumberFormat("en", { style: "currency", currency: code, currencyDisplay: "name" }).formatToParts(2);
    return parts.find((part) => part.type === "currency")?.value ?? code;
  } catch {
    return code;
  }
}

/**
 * The header's line under a pay figure whose currency the posting did not state (`salary_currency_assumed`, a bare
 * "$" included): what it was read as and why, from data alone ("Pay read as Canadian dollars, job is in Canada").
 * Capture takes the job's country's currency, else the home one (backend `routers/jobs._salary_currency_for`), so
 * `country` is the job's country by name, or null when the job names none.
 */
export function assumedCurrencyLine(currency: string, country: string | null): string {
  const words = currencyWords(currency);
  return country ? `Pay read as ${words}, job is in ${country}` : `Pay read as ${words}, your home currency`;
}
