// A number moving to its new value (visual-language plan, Task 15). Pure, so node tests it.
export function easeOutCubic(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return 1 - (1 - c) ** 3;
}

export function valueAt(from: number, to: number, t: number): number {
  return from + (to - from) * easeOutCubic(t);
}
