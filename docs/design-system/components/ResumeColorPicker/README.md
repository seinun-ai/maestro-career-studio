A resume color picker chooses a base resume's color: ten preset swatches and a custom hue.

**You provide:** `value` (the hue, or null), `onChange(hue)`, and `used`, the other resumes' hues with their names. Optionally `onCommit(hue)`, a `label` (default "Color") and `pickedAtRandom`, which shows the hint "Picked at random from colors no other resume uses."; the caller turns it off on the first choice.

- A `radiogroup` of ten 32px swatches, each a `button` with `role="radio"` and `aria-checked`, `radius-corner-sm` (a control) and the preset's `resume` fill. The accessible name is the preset's name, plus ", used by <names>" when another resume has it.
- `onChange` is the live value: every swatch click, arrow key and slider input. A form that only holds the value (the New base resume dialog) uses it alone. `onCommit` fires once per settled choice: a swatch click, the keyup after an arrow, Home or End, and the slider's pointerup, keyup or blur. A caller that saves each choice (the Target dialog) saves on `onCommit`, so a drag sends one request.
- The checked swatch draws a 16px `Check` in `primary-foreground` and the solid 2px `ring` outline with an offset. Focus is a separate solid `ring` (a 2px box-shadow, 4px out, over a `card` offset) outside that outline, so a focused swatch never looks checked, and the checked, focused one shows both.
- Arrow keys, Home and End move between swatches and choose as they go; one swatch is in the tab order (the checked one, else the first).
- A taken preset is not disabled: two resumes may share a color. It carries a small `card` dot in its corner and its name in the accessible name, never a faded fill (a faded fill reads as disabled).
- "Custom" is an outline button (`aria-expanded`) that opens a "Hue" slider (open on its own while the value is a custom hue), a native range input from 0 to 359, spoken as the preset's name or "Hue 120", over a gradient track drawn from the same recipe as the square. The thumb is a small bar, not a dot.

Source: `frontend/components/base-resumes/resume-color-picker.tsx`.
