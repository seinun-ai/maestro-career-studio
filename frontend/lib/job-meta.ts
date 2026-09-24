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
