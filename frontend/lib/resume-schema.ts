import { z } from "zod";

export const contactSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.string().email("Invalid email"),
  phone: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  linkedin: z.string().nullable().optional(),
  github: z.string().nullable().optional(),
  website: z.string().nullable().optional(),
});

export const experienceSchema = z.object({
  company: z.string().min(1),
  role: z.string().min(1),
  location: z.string().nullable().optional(),
  start_date: z.string().min(1),
  end_date: z.string().nullable().optional(),
  enabled: z.boolean().default(true),
  bullets: z.array(z.string()).default([]),
});

export const educationSchema = z.object({
  institution: z.string().min(1),
  degree: z.string().min(1),
  field: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  graduation_date: z.string().nullable().optional(),
  gpa: z.string().nullable().optional(),
  coursework: z.array(z.string()).default([]),
  bullets: z.array(z.string()).default([]),
});

export const projectSchema = z.object({
  name: z.string().min(1),
  enabled: z.boolean().default(true),
  tech: z.string().nullable().optional(),
  link: z.string().nullable().optional(),
  date: z.string().nullable().optional(),
  bullets: z.array(z.string()).default([]),
});

export const skillGroupSchema = z.object({
  category: z.string().min(1),
  items: z.array(z.string()).default([]),
});

// --- Custom (extra) sections -------------------------------------------------
// Mirrors backend `app/schemas/resume.py`. The section base forbids stray keys
// (backend `extra="forbid"`): the `.strict()` variants reject a wrong-branch
// content field — e.g. `bullets` on an `entries` section — instead of silently
// stripping it, so a miswired section fails visibly rather than losing content.
// Entries themselves mirror the backend's lenient `ExtraSectionEntry` (no
// forbid), so they are NOT strict.

/** Core section field names an extra-section key may not shadow. */
export const CORE_SECTION_KEYS = new Set([
  "contact",
  "summary",
  "skills",
  "experience",
  "projects",
  "education",
  "certifications",
]);

/** Display headers a core section already prints. An extra-section TITLE equal
 *  to one of these (case-insensitively) would render a duplicate PDF header.
 *  Mirrors backend `app/schemas/resume.py` CORE_SECTION_TITLES (keep in sync). */
export const CORE_SECTION_TITLES = new Set([
  "summary",
  "skills",
  "technical skills",
  "experience",
  "projects",
  "education",
  "certifications",
]);

/** Shared with backend `TITLE_COLLISION_MESSAGE` (keep the copy identical). */
export const TITLE_COLLISION_MESSAGE =
  "Title collides with a core section header. Choose a different title.";

/** True when `title` (trimmed, case-folded) matches a core section header. */
export function isCoreSectionTitle(title: string): boolean {
  return CORE_SECTION_TITLES.has(title.trim().toLowerCase());
}

/** Lowercase slug: starts alphanumeric, then alphanumeric / underscore / hyphen. */
export const SECTION_KEY_RE = /^[a-z0-9][a-z0-9_-]*$/;

const SECTION_KEY_MESSAGE =
  "section key must be a lowercase slug (alphanumeric, '_' or '-'), e.g. 'publications'";

/** Non-empty title that must not collide with a core section header. */
const extraSectionTitleSchema = z
  .string()
  .min(1)
  .refine((t) => !isCoreSectionTitle(t), TITLE_COLLISION_MESSAGE);

export const extraSectionEntrySchema = z.object({
  heading: z.string().min(1),
  subheading: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  date: z.string().nullable().optional(),
  link: z.string().nullable().optional(),
  enabled: z.boolean().default(true),
  bullets: z.array(z.string()).default([]),
});

export const extraSectionEntriesSchema = z
  .object({
    key: z.string().regex(SECTION_KEY_RE, SECTION_KEY_MESSAGE),
    title: extraSectionTitleSchema,
    enabled: z.boolean().default(true),
    type: z.literal("entries"),
    entries: z.array(extraSectionEntrySchema).default([]),
  })
  .strict();

export const extraSectionBulletsSchema = z
  .object({
    key: z.string().regex(SECTION_KEY_RE, SECTION_KEY_MESSAGE),
    title: extraSectionTitleSchema,
    enabled: z.boolean().default(true),
    type: z.literal("bullets"),
    bullets: z.array(z.string()).default([]),
  })
  .strict();

export const extraSectionSchema = z.discriminatedUnion("type", [
  extraSectionEntriesSchema,
  extraSectionBulletsSchema,
]);

/** Mirrors backend `ResumeData._unique_non_reserved_keys`: keys are unique
 *  case-insensitively and may not collide with a core section name. */
const extraSectionsArraySchema = z
  .array(extraSectionSchema)
  .superRefine((sections, ctx) => {
    const seen = new Set<string>();
    sections.forEach((section, i) => {
      const folded = section.key.toLowerCase();
      if (CORE_SECTION_KEYS.has(folded)) {
        ctx.addIssue({
          code: "custom",
          path: [i, "key"],
          message: `extra section key '${section.key}' collides with the core '${folded}' section`,
        });
      } else if (seen.has(folded)) {
        ctx.addIssue({
          code: "custom",
          path: [i, "key"],
          message: `duplicate extra section key '${section.key}'`,
        });
      }
      seen.add(folded);
    });
  });

export const resumeDataSchema = z.object({
  contact: contactSchema,
  summary: z.string().nullable().optional(),
  skills: z.array(skillGroupSchema).default([]),
  experience: z.array(experienceSchema).default([]),
  projects: z.array(projectSchema).default([]),
  education: z.array(educationSchema).default([]),
  certifications: z.array(z.string()).default([]),
  extra_sections: extraSectionsArraySchema.default([]),
});

export type ResumeDataInput = z.input<typeof resumeDataSchema>;
