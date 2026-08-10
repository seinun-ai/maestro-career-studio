

/** Human label for a `role_category` slug.
 *
 * The backend stores snake_case keys (`bi_developer`) and analytics endpoints
 * return them raw, so charts were rendering the slug verbatim — including a
 * bare "other" with no explanation. Kept as a pure client-side humanizer rather
 * than a second copy of the vocabulary: the canonical list lives in
 * backend/app/services/ats/data/role_categories.yaml, and duplicating it here
 * would recreate exactly the drift this change removed.
 */
export function roleCategoryLabel(key: string | null | undefined): string {
  if (!key) return "Unknown";
  const special: Record<string, string> = {
    other: "Other",
    unknown: "Unknown",
    ai_ml_engineer: "AI/ML Engineer",
    bi_developer: "BI Developer",
    mlops_engineer: "MLOps Engineer",
  };
  if (special[key]) return special[key];
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
