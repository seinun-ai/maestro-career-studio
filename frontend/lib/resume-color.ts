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

/** The `resume` colour's lightness and its chroma multiple in the current theme. */
export type SwatchTones = { l: number; c: number };

/** The tones from `--resume-swatch-l` and `--resume-swatch-c` (globals.css declares them per theme and is
 *  their only home). `null` when either is not a plain number. */
export function parseSwatchTones(l: string, c: string): SwatchTones | null {
  const tones = { l: Number.parseFloat(l), c: Number.parseFloat(c) };
  return Number.isFinite(tones.l) && Number.isFinite(tones.c) ? tones : null;
}

/** The `resume` colour as a literal `oklch()`, for an SVG fill that a CSS class cannot reach (a chart's
 *  bars). Same recipe as `--color-resume` in globals.css, with the tones the caller read from there. No
 *  hue draws grey; no tones yet draws the text colour. */
export function resumeSwatchColor(hue: number | null | undefined, tones: SwatchTones | null): string {
  if (!tones) return "currentColor";
  const chroma = hue === null || hue === undefined ? 0 : resumeChroma(hue) * tones.c;
  return `oklch(${tones.l} ${Math.round(chroma * 1e4) / 1e4} ${hue ?? 0})`;
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
