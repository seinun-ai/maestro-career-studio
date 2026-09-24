/**
 * The sidebar section a route belongs to when its URL does not say so. A job
 * page is a row of the Jobs page (`/applications`) unless it
 * was opened from the proposals queue, whose Back button it then shows.
 *
 * `from` is the `?from=` value: `null` when the URL has none, `undefined` when
 * it is not known yet (the static fallback rendered before the search params
 * are read). A job page with an unknown `from` belongs to NO section, so the
 * fallback never marks the wrong one; every other route ignores `from`.
 */
export function navSection(pathname: string, from?: string | null): string | null {
  if (pathname === "/jobs" || pathname.startsWith("/jobs/")) {
    if (from === undefined) return null;
    return from === "proposals" ? "/proposals" : "/applications";
  }
  return pathname;
}

/**
 * `aria-current` for a sidebar destination (WCAG technique ARIA26).
 *
 * "page" when the route IS the destination; "true" when it is inside it (a
 * base-resume studio under Base Resumes, a job page under its section), so
 * exactly one item in the set is current either way. `undefined` omits the
 * attribute.
 */
export function navCurrent(
  pathname: string,
  href: string,
  from?: string | null,
): "page" | "true" | undefined {
  if (pathname === href) return "page";
  const section = navSection(pathname, from);
  if (section !== null && (section === href || section.startsWith(`${href}/`))) return "true";
  return undefined;
}
