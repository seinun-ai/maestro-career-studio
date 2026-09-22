/**
 * The sidebar section a route belongs to when its URL does not say so. A job
 * page is a row of the Applications tracker (Saved jobs included) unless it
 * was opened from the proposals queue, whose Back button it then shows.
 */
export function navSection(pathname: string, from?: string | null): string {
  if (pathname === "/jobs" || pathname.startsWith("/jobs/")) {
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
  if (section === href || section.startsWith(`${href}/`)) return "true";
  return undefined;
}
