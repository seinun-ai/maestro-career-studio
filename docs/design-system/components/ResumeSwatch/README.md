A resume swatch is a base resume's color as a small square beside its name; a resume tag is the square and the name together.

**You provide:** `ResumeSwatch` takes the resume's `hue` (0-359, or null for neutral grey); `ResumeTag` takes the `hue` and the name as its children. Both take an optional `className`. To get a hue from a resume's slug, take `const colorOf = useBaseResumeColor()` once and call `colorOf(slug)` per row, as `useBaseResumeLabel` works.

- 10px square, `radius-corner-2xs` (2px), filled with `resume`. The hue and its chroma ride on the element as `--resume-h` and `--resume-c` (`resumeColorStyle` in `lib/resume-color.ts`); `globals.css` turns them into `resume`, `resume-container` and `on-resume-container`. A resume with no hue draws grey.
- Never round (round is status) and never faded (a faded fill reads as disabled). Never alone: the name sits beside it, so the square is hidden from assistive tech.
- `ResumeTag` is `inline-flex`, `gap-1.5`, the square first.
- A card that stands for one base resume adds a 6px `resume` top band (the gallery card also a `resume-container` footer with `on-resume-container` text; the score card, the band only); set `resumeColorStyle(hue)` on the card so its children inherit the hue.
- The ten presets are Rose, Copper, Ochre, Olive, Pine, Teal, Sky, Slate, Iris and Plum. A custom hue uses chroma 0.10. The preset table is mirrored by the backend (`app/services/resume_colors.py`) and pinned equal by `test_resume_color_parity.py`.

Source: `frontend/components/visual/resume-swatch.tsx`, `frontend/lib/resume-color.ts`.
