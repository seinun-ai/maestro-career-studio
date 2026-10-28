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
 * Whether the header explains a pay figure whose currency the posting did not state: only for a job in another
 * country than where you live (owner, 2026-10-22). Capture reads such pay as the job's country's currency, else the
 * home one (backend `routers/jobs._salary_currency_for`), so a job at home or one naming no country was read as your
 * own currency and the line would only add noise. `home` is the home market's ISO code: null for a market with no
 * country, undefined until the setting loads (then nothing shows, so the line never flashes in and out).
 */
export function showsAssumedCurrency(job: string | null | undefined, home: string | null | undefined): boolean {
  if (!job || home === undefined) return false;
  return job.toUpperCase() !== home?.toUpperCase();
}

/**
 * The header's line under a pay figure whose currency the posting did not state (`salary_currency_assumed`, a bare
 * "$" included) when `showsAssumedCurrency` says so: what it was read as and why ("Pay read as Canadian dollars, job
 * is in Canada"). `country` is the job's country by name.
 */
export function assumedCurrencyLine(currency: string, country: string): string {
  return `Pay read as ${currencyWords(currency)}, job is in ${country}`;
}

/**
 * The work mode unless the location already names it: "Remote (United States) · Remote" read the mode twice. A whole
 * word only, whatever its case, so "Remoteville" keeps it. `mode` is the mode in words ("Remote", "On-site").
 */
export function workModeUnlessSaid(location: string | null | undefined, mode: string | null | undefined): string | null {
  if (!mode) return null;
  const word = mode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return location && new RegExp(`(^|[^\\w-])${word}($|[^\\w-])`, "i").test(location) ? null : mode;
}

/**
 * Whether the job details show the OPT line. OPT is a US student work permit, so the line shows for a job in the
 * United States, or when the posting says anything about it; an unstated line on a UK job was noise.
 */
export function showsOptLine(opt: string | null | undefined, country: string | null | undefined): boolean {
  const stated = !!opt && opt !== "unstated" && opt !== "unknown";
  return stated || country?.toUpperCase() === "US";
}
