/**
 * Structured formatting knobs mirrored from the backend `ResumeFormatting`
 * schema (`backend/app/schemas/formatting.py`). Defaults MUST stay in lockstep
 * with that schema — they reproduce the seeded Classic template's output, so a
 * resume with no stored formatting renders unchanged.
 */

export type ResumeFormatting = {
  font_size: 10 | 11 | 12;
  side_margins: number;
  top_bottom_margin: number;
  section_spacing: number;
  entry_spacing: number;
  line_spacing: number;
  bullet_icon: "bullet" | "dash";
  hide_divider: boolean;
  header_align: "left" | "center" | "right";
  justify: boolean;
  date_format: "verbatim" | "short_month" | "long_month" | "numeric";
  education_order: "degree_first" | "institution_first";
  skills_layout: "inline" | "bulleted";
  /**
   * Render order of the resume's sections. `null` means "the template's own
   * order" — the backend never rewrites it to an explicit list, so an
   * untouched resume keeps inheriting whatever order its template ships with.
   * A partial list orders its members first and the template appends the rest.
   */
  section_order: SectionKey[] | null;
};

export type SectionKey =
  | "summary"
  | "experience"
  | "projects"
  | "extra_sections"
  | "skills"
  | "education"
  | "certifications";

export const FORMATTING_DEFAULTS: ResumeFormatting = {
  font_size: 11,
  side_margins: 0.4,
  top_bottom_margin: 0.3,
  section_spacing: 6,
  entry_spacing: 0,
  line_spacing: 1.0,
  bullet_icon: "bullet",
  hide_divider: false,
  header_align: "center",
  justify: false,
  date_format: "verbatim",
  education_order: "degree_first",
  skills_layout: "inline",
  section_order: null,
};

/**
 * Row labels for the section-order control. "Custom sections" names the whole
 * `extra_sections` RUN: this knob moves the block, while the editor's
 * move-section buttons order the custom sections among themselves — two
 * mechanisms, and the label is what keeps the split legible.
 */
export const SECTION_ORDER_LABELS: Record<SectionKey, string> = {
  summary: "Summary",
  experience: "Experience",
  projects: "Projects",
  extra_sections: "Custom sections",
  skills: "Skills",
  education: "Education",
  certifications: "Certifications",
};

/**
 * What the control shows when nothing is stored (`section_order: null`).
 *
 * Deliberately NOT every key in {@link SECTION_ORDER_LABELS}: `certifications`
 * is a standalone section in only one bundled template, and listing a row the
 * selected template folds into Skills would promise a move that does nothing.
 * A template that renders certs standalone ships an explicit `section_order` in
 * its `default_formatting`, which arrives here as the panel baseline and brings
 * the row with it.
 */
export const SECTION_ORDER_FALLBACK: SectionKey[] = [
  "summary",
  "experience",
  "projects",
  "extra_sections",
  "skills",
  "education",
];

/** Option labels for the choice-style knobs. */
export const DATE_FORMAT_OPTIONS: { value: ResumeFormatting["date_format"]; label: string }[] = [
  { value: "verbatim", label: "As written" },
  { value: "short_month", label: "Jun 2026" },
  { value: "long_month", label: "June 2026" },
  { value: "numeric", label: "06/2026" },
];

export const BULLET_ICON_OPTIONS: { value: ResumeFormatting["bullet_icon"]; label: string }[] = [
  { value: "bullet", label: "•" },
  { value: "dash", label: "–" },
];

export const HEADER_ALIGN_OPTIONS: { value: ResumeFormatting["header_align"]; label: string }[] = [
  { value: "left", label: "Left" },
  { value: "center", label: "Center" },
  { value: "right", label: "Right" },
];

export const EDUCATION_ORDER_OPTIONS: {
  value: ResumeFormatting["education_order"];
  label: string;
}[] = [
  { value: "degree_first", label: "Degree first" },
  { value: "institution_first", label: "School first" },
];

export const SKILLS_LAYOUT_OPTIONS: { value: ResumeFormatting["skills_layout"]; label: string }[] = [
  { value: "inline", label: "Inline" },
  { value: "bulleted", label: "Bulleted" },
];

export const FONT_SIZE_OPTIONS: { value: ResumeFormatting["font_size"]; label: string }[] = [
  { value: 10, label: "10pt" },
  { value: 11, label: "11pt" },
  { value: 12, label: "12pt" },
];

/** Slider ranges mirror the Pydantic `Field(ge=…, le=…)` bounds. */
export const SLIDER_RANGES = {
  section_spacing: { min: 0, max: 14, step: 1 },
  entry_spacing: { min: 0, max: 10, step: 1 },
  line_spacing: { min: 0.9, max: 1.4, step: 0.1 },
  top_bottom_margin: { min: 0.3, max: 1.0, step: 0.05 },
  side_margins: { min: 0.3, max: 1.0, step: 0.05 },
} as const;

/**
 * Return only the keys of `value` that differ from `baseline`, or `null` when
 * nothing differs. Storing the diff keeps "uncustomized" as `null` so the
 * backend inherits/merges correctly.
 *
 * In the base editor the baseline is {@link FORMATTING_DEFAULTS}. In the studio
 * it is defaults merged with the base resume's formatting, so an application
 * only stores genuine overrides of what it inherits — and can still override an
 * inherited non-default value back to a default (which differs from baseline).
 */
export function diffFrom(
  baseline: ResumeFormatting,
  value: Partial<ResumeFormatting>,
): Partial<ResumeFormatting> | null {
  const out: Partial<ResumeFormatting> = {};
  for (const key of Object.keys(FORMATTING_DEFAULTS) as (keyof ResumeFormatting)[]) {
    const v = value[key];
    if (v !== undefined && !sameFormattingValue(v, baseline[key])) {
      (out as Record<string, unknown>)[key] = v;
    }
  }
  return Object.keys(out).length ? out : null;
}

/**
 * Value equality for one knob. Every knob but `section_order` is a primitive,
 * where `===` is equality; a list compares element-wise AND order-sensitively,
 * because for this knob the order IS the value. Reference `!==` would report
 * every freshly-built array as an override and store a redundant copy of the
 * inherited order on every render.
 */
function sameFormattingValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    return (
      Array.isArray(a) &&
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((item, index) => item === b[index])
    );
  }
  return a === b;
}

/** Diff against the plain defaults — the base-editor case. */
export function diffFromDefaults(
  value: Partial<ResumeFormatting>,
): Partial<ResumeFormatting> | null {
  return diffFrom(FORMATTING_DEFAULTS, value);
}
