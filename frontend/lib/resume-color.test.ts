import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RESUME_PRESETS,
  pickFreeHue,
  presetName,
  resumeChroma,
  resumeColorStyle,
  resumeFill,
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

test("the chart fill is the swatch recipe with the theme's tones left to CSS", () => {
  assert.equal(resumeFill(5), "oklch(var(--resume-swatch-l) calc(0.11 * var(--resume-swatch-c)) 5)");
  // A custom hue takes the custom chroma.
  assert.equal(resumeFill(41), "oklch(var(--resume-swatch-l) calc(0.1 * var(--resume-swatch-c)) 41)");
});

test("no hue draws grey", () => {
  assert.equal(resumeFill(null), "oklch(var(--resume-swatch-l) calc(0 * var(--resume-swatch-c)) 0)");
});
