/** Slugs are an internal identifier — derived from the display name, never
 *  typed or shown (user ask, 2026-07-16). Shared so the create and duplicate
 *  paths cannot drift on how a name becomes an id. */
export function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "resume"
  );
}

/** `slugify`, then suffix a counter until it does not collide with `taken`. */
export function uniqueSlug(name: string, taken: Iterable<string>): string {
  const base = slugify(name);
  const used = new Set(taken);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}
