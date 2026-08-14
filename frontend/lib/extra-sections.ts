import {
  CORE_SECTION_KEYS,
  SECTION_KEY_RE,
  TITLE_COLLISION_MESSAGE,
  isCoreSectionTitle,
} from "@/lib/resume-schema";
import type {
  ExtraSection,
  ExtraSectionEntry,
  ExtraSectionType,
} from "@/lib/types";

export {
  CORE_SECTION_KEYS,
  SECTION_KEY_RE,
  TITLE_COLLISION_MESSAGE,
  isCoreSectionTitle,
};

/**
 * Slugify a display name into a lowercase key candidate. Non-alphanumeric runs
 * become single hyphens; leading/trailing hyphens are trimmed. May return "" for
 * a name with no alphanumeric characters (caller falls back).
 */
export function slugifyKey(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Derive a stable, valid, unique section key from a display name. Guarantees:
 * matches {@link SECTION_KEY_RE}, does not collide with a core section field
 * name, and is unique (case-insensitively) among `existingKeys`. The key is
 * identity only — it is never shown to the user.
 */
export function uniqueSectionKey(
  name: string,
  existingKeys: Iterable<string>,
): string {
  const taken = new Set<string>(CORE_SECTION_KEYS);
  for (const key of existingKeys) taken.add(key.toLowerCase());

  let base = slugifyKey(name);
  // A digits-only slug is still a valid slug; only an empty/invalid one needs a
  // fallback stem.
  if (!base || !SECTION_KEY_RE.test(base)) base = "section";

  let candidate = base;
  let n = 2;
  while (taken.has(candidate)) {
    candidate = `${base}-${n}`;
    n += 1;
  }
  return candidate;
}

export const SECTION_TYPE_LABELS: Record<ExtraSectionType, string> = {
  entries: "Entries",
  bullets: "Bullets",
};

const EMPTY_ENTRY: ExtraSectionEntry = {
  heading: "",
  subheading: "",
  location: "",
  date: "",
  link: "",
  enabled: true,
  bullets: [],
};

export function emptyEntry(): ExtraSectionEntry {
  return { ...EMPTY_ENTRY, bullets: [] };
}

/** Build a fresh, empty section of the given type with a resolved unique key. */
export function newSection(
  name: string,
  type: ExtraSectionType,
  existingKeys: Iterable<string>,
): ExtraSection {
  const key = uniqueSectionKey(name, existingKeys);
  const title = name.trim();
  if (type === "entries") {
    return { key, title, enabled: true, type: "entries", entries: [] };
  }
  return { key, title, enabled: true, type: "bullets", bullets: [] };
}

export interface SectionPreset {
  id: string;
  label: string;
  /** Prefilled section title. */
  title: string;
  type: ExtraSectionType;
}

/**
 * Presets only prefill title + type; the stored shape is identical to a
 * hand-built section. Synchronized with backend/app/services/extra_section_presets.py.
 */
export const SECTION_PRESETS: SectionPreset[] = [
  { id: "publications", label: "Publications", title: "Publications", type: "entries" },
  { id: "presentations", label: "Presentations & Talks", title: "Presentations & Talks", type: "entries" },
  { id: "volunteer", label: "Volunteer Experience", title: "Volunteer Experience", type: "entries" },
  { id: "awards", label: "Awards & Honors", title: "Awards & Honors", type: "bullets" },
  { id: "languages", label: "Languages", title: "Languages", type: "bullets" },
  { id: "licenses", label: "Licenses", title: "Licenses", type: "bullets" },
  { id: "clearance", label: "Security Clearance", title: "Security Clearance", type: "bullets" },
  { id: "memberships", label: "Professional Affiliations", title: "Professional Affiliations", type: "bullets" },
];

export function isEnabled(value: { enabled?: boolean }): boolean {
  return value.enabled !== false;
}


