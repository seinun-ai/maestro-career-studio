import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RESUME_PRESETS,
  parseSwatchTones,
  pickFreeHue,
  presetName,
  resumeChroma,
  resumeColorStyle,
  resumeSwatchColor,
} from "./resume-color.ts";

const HUES = RESUME_PRESETS.map((p) => p.hue);

test("a preset keeps its chroma and any other hue gets the custom one", () => {
  assert.equal(resumeChroma(265), 0.06);
  assert.equal(resumeChroma(266), 0.1);
});

test("no hue sets no variables, so the colours fall back to grey", () => {
  assert.deepEqual(resumeColorStyle(null), {});
  assert.deepEqual(resumeColorStyle(undefined), {});
  assert.deepEqual(resumeColorStyle(40), { "--resume-h": 40, "--resume-c": 0.11 });
});

test("pickFreeHue takes a hue nobody has", () => {
  const taken = HUES.slice(0, 9);
  assert.equal(pickFreeHue(taken, () => 0.99), HUES[9]);
});

test("pickFreeHue spreads over the least-used presets once all are taken", () => {
  const used = [...HUES, ...HUES.slice(1)];
  assert.equal(pickFreeHue(used, () => 0.5), HUES[0]);
});

test("pickFreeHue ignores custom and missing hues", () => {
  const used = [null, 1, 2, 3];
  const picks = new Set(HUES.map((_, i) => pickFreeHue(used, () => i / HUES.length)));
  assert.equal(picks.size, HUES.length);
});

test("presetName names a preset and nothing else", () => {
  assert.equal(presetName(195), "Teal");
  assert.equal(presetName(196), null);
  assert.equal(presetName(null), null);
});

test("the tones are read from the CSS variables' text, and junk reads as no tones", () => {
  assert.deepEqual(parseSwatchTones(" 0.52", " 1"), { l: 0.52, c: 1 });
  assert.equal(parseSwatchTones("", ""), null);
  assert.equal(parseSwatchTones("0.52", "calc(1)"), null);
});

test("the chart colour is the swatch recipe: the theme's lightness, the hue's chroma times the theme's multiple", () => {
  assert.equal(resumeSwatchColor(5, { l: 0.52, c: 1 }), "oklch(0.52 0.11 5)");
  assert.equal(resumeSwatchColor(160, { l: 0.76, c: 0.9 }), "oklch(0.76 0.081 160)");
  // A custom hue takes the custom chroma.
  assert.equal(resumeSwatchColor(41, { l: 0.52, c: 1 }), "oklch(0.52 0.1 41)");
});

test("no hue draws grey, and no tones yet draws the text colour", () => {
  assert.equal(resumeSwatchColor(null, { l: 0.52, c: 1 }), "oklch(0.52 0 0)");
  assert.equal(resumeSwatchColor(5, null), "currentColor");
});
