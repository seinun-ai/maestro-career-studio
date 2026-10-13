A resume color picker chooses a base resume's color: ten preset swatches and a custom hue.

**You provide:** `value` (the hue, or null), `onChange(hue)` and `used`, the other resumes' hues with their names. Optionally a `label` (default "Color") and `pickedAtRandom`, which shows the hint "Picked at random from colors no other resume uses." until the person chooses.

- A `radiogroup` of ten 32px swatches, each a `button` with `role="radio"` and `aria-checked`, `radius-corner-sm` (a control) and the preset's `resume` fill. The accessible name is the preset's name, plus ", used by <names>" when another resume has it.
- The checked swatch draws a 16px `Check` in `primary-foreground` and the solid 2px `ring` outline with an offset. Focus is the same ring.
- Arrow keys, Home and End move between swatches and choose as they go; one swatch is in the tab order (the checked one, else the first).
- A taken preset is not disabled: two resumes may share a color. It carries a small `card` dot in its corner and its name in the accessible name, never a faded fill (a faded fill reads as disabled).
- "Custom" is an outline button (`aria-expanded`) that opens a "Hue" slider, a native range input from 0 to 359 over a gradient track drawn from the same recipe as the square. The thumb is a small bar, not a dot.

Source: `frontend/components/base-resumes/resume-color-picker.tsx`.
