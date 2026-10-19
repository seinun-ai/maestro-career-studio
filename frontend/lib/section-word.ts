import { SECTION_ORDER_LABELS, type SectionKey } from "@/lib/formatting";

/** A resume section's name ("extra" is the importer's key for Other sections). */
export function sectionWord(section: string): string {
  const key = (section === "extra" ? "extra_sections" : section) as SectionKey;
  return SECTION_ORDER_LABELS[key] ?? "Other sections";
}
