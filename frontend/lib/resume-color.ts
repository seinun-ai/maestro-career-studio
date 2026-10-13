import type { CSSProperties } from "react";

/** A base resume's colour is identity, never state: a square beside its name.
 *  Only the hue is stored; globals.css derives the tones. Mirrors
 *  backend/app/services/resume_colors.py (pinned by test_resume_color_parity.py). */
export const RESUME_PRESETS = [
  { name: "Rose", hue: 5, chroma: 0.11 },
  { name: "Copper", hue: 40, chroma: 0.11 },
  { name: "Ochre", hue: 80, chroma: 0.11 },
  { name: "Olive", hue: 125, chroma: 0.11 },
  { name: "Pine", hue: 160, chroma: 0.09 },
  { name: "Teal", hue: 195, chroma: 0.09 },
  { name: "Sky", hue: 230, chroma: 0.09 },
  { name: "Slate", hue: 265, chroma: 0.06 },
  { name: "Iris", hue: 300, chroma: 0.11 },
  { name: "Plum", hue: 335, chroma: 0.11 },
] as const;

export const CUSTOM_CHROMA = 0.1;

export function resumeChroma(hue: number): number {
  return RESUME_PRESETS.find((p) => p.hue === hue)?.chroma ?? CUSTOM_CHROMA;
}

/** The CSS variables that colour `bg-resume`, `bg-resume-container` and
 *  `text-on-resume-container` on this element and its children. No hue sets
 *  nothing, and the colours fall back to neutral grey. */
export function resumeColorStyle(hue: number | null | undefined): CSSProperties {
  if (hue === null || hue === undefined) return {};
  return { "--resume-h": hue, "--resume-c": resumeChroma(hue) } as CSSProperties;
}

/** The `resume` colour as a CSS string for an SVG fill that a class cannot reach (a chart's bars). The
 *  recipe of `--color-resume` in globals.css, with the theme's tones left as `var()`s: the browser
 *  resolves them, so light and dark follow the theme with no JS. No hue draws grey. */
export function resumeFill(hue: number | null | undefined): string {
  const chroma = hue === null || hue === undefined ? 0 : resumeChroma(hue);
  return `oklch(var(--resume-swatch-l) calc(${chroma} * var(--resume-swatch-c)) ${hue ?? 0})`;
}

/** A random preset no hue in `used` has; else one of the least-used. Same rule as the server. */
export function pickFreeHue(used: (number | null)[], random = Math.random): number {
  const counts = new Map<number, number>();
  for (const h of used) {
    if (h !== null && RESUME_PRESETS.some((p) => p.hue === h)) counts.set(h, (counts.get(h) ?? 0) + 1);
  }
  const fewest = Math.min(...RESUME_PRESETS.map((p) => counts.get(p.hue) ?? 0));
  const free = RESUME_PRESETS.filter((p) => (counts.get(p.hue) ?? 0) === fewest);
  return free[Math.floor(random() * free.length)].hue;
}

export function presetName(hue: number | null | undefined): string | null {
  return RESUME_PRESETS.find((p) => p.hue === hue)?.name ?? null;
}
