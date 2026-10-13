/* Maestro CS Companion — a base resume's colour, as the app draws it.
 *
 * A base resume's colour is identity, never state: one stored hue (`color_hue`) drawn as a small square before the
 * resume's name. Only the hue travels; the panel turns it into a colour with the recipe in panel.css (`.swatch` and
 * the `--cs-resume-*` tones). The chroma rides with the hue because the presets are tuned per hue.
 *
 * The same ten presets and the same custom chroma as frontend/lib/resume-color.ts and
 * backend/app/services/resume_colors.py, across the extension boundary where no import reaches:
 * `backend/tests/test_resume_color_parity.py` fails if they drift. Loaded by the panel document only
 * (panel.html); panel.js throws at boot naming this file when it did not publish.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const PRESETS = [
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
  ];

  const CUSTOM_CHROMA = 0.1;

  /** The chroma a hue is drawn with: its preset's, else the custom one. */
  ns.resumeChroma = (hue) => PRESETS.find((preset) => preset.hue === hue)?.chroma ?? CUSTOM_CHROMA;
})();
