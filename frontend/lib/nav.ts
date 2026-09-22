/**
 * `aria-current` for a sidebar destination (WCAG technique ARIA26).
 *
 * "page" when the route IS the destination; "true" when it is inside it (a
 * base-resume studio under Base Resumes), so exactly one item in the set is
 * current either way. `undefined` omits the attribute.
 */
export function navCurrent(
  pathname: string,
  href: string,
): "page" | "true" | undefined {
  if (pathname === href) return "page";
  if (pathname.startsWith(`${href}/`)) return "true";
  return undefined;
}
