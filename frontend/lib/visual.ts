// Pure helpers behind components/visual (visual-language plan, Task 14). Node tests load this directly.

export function clampPct(value: number, max = 100): number {
  if (!Number.isFinite(value) || !(max > 0)) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

export type DeltaSign = "up" | "down" | "flat";

/** "+6.2" / "−1.4" (a true minus sign) / "0.0", and which way it went. */
export function formatDelta(value: number, digits = 1): { text: string; sign: DeltaSign } {
  const snapped = Number.isFinite(value) ? Number(value.toFixed(digits)) : 0;
  if (snapped === 0) return { text: (0).toFixed(digits), sign: "flat" };
  const text = `${snapped > 0 ? "+" : "−"}${Math.abs(snapped).toFixed(digits)}`;
  return { text, sign: snapped > 0 ? "up" : "down" };
}

export function meterLabel(name: string, filled: number, total: number, word: string): string {
  return `${name} ${filled} of ${total}: ${word}`;
}

export function segmentShares<K extends string>(parts: { key: K; count: number }[]): { key: K; share: number }[] {
  const own = (p: { count: number }) => (Number.isFinite(p.count) ? Math.max(0, p.count) : 0);
  const total = parts.reduce((sum, p) => sum + own(p), 0);
  return parts.map((p) => ({ key: p.key, share: total === 0 ? 0 : (own(p) / total) * 100 }));
}

function sparkPoints(input: number[], width: number, height: number): { x: number; y: number }[] {
  const finite = input.filter(Number.isFinite);
  // One value is a flat line across the box: two points, same y.
  const values = finite.length === 1 ? [finite[0], finite[0]] : finite;
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const stepX = width / (values.length - 1);
  return values.map((v, i) => ({
    x: +(i * stepX).toFixed(2),
    y: +(span === 0 ? height / 2 : height - ((v - min) / span) * height).toFixed(2),
  }));
}

/** An SVG path through `values`, x spread across `width`, y scaled into `height` (top = max). */
export function sparkPath(values: number[], width: number, height: number): string {
  return sparkPoints(values, width, height)
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${p.y}`)
    .join(" ");
}

/** Where the line ends (the dot), in the same box as `sparkPath`; null for an empty series. */
export function sparkEnd(values: number[], width: number, height: number): { x: number; y: number } | null {
  return sparkPoints(values, width, height).at(-1) ?? null;
}
