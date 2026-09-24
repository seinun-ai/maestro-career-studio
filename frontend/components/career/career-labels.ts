import type { KBEntityKind, KBEntityStatus } from "@/lib/types";

/**
 * The words for a career history item's kind and status, on every surface that
 * names one (the item card and page, Add item, Merge, New base resume, Add from
 * career history). One table, so a kind is never "Custom section" on one screen
 * and "Other section" on the next, and a status never prints its stored key.
 */
export const KB_KIND_LABELS: Record<KBEntityKind, string> = {
  experience: "Experience",
  project: "Project",
  education: "Education",
  certification: "Certification",
  extra: "Other section",
};

export const KB_STATUS_LABELS: Record<KBEntityStatus, string> = {
  ongoing: "Ongoing",
  completed: "Completed",
  archived: "Archived",
};

/** A stored status in words; a value the table lacks reads "Unknown", never the key. */
export function kbStatusLabel(status: string | null | undefined): string {
  return Object.hasOwn(KB_STATUS_LABELS, status ?? "")
    ? KB_STATUS_LABELS[status as KBEntityStatus]
    : "Unknown";
}
