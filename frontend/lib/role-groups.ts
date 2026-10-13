/** The role fields a base resume carries. `role_category` is "unknown" when no role is declared. */
type RoleFields = { role_category: string; role_label: string | null };

/** No role declared: the storage sentinel with no free-text label. */
export function isRoleUnset(resume: RoleFields): boolean {
  return resume.role_category === "unknown" && !resume.role_label;
}

export type RoleGroup<T> = {
  /** Stable across renders: the free-text label (any case) or the catalog category. "" for the unset group. */
  key: string;
  /** The first member's display label. `null` for the unset group. */
  label: string | null;
  resumes: T[];
};

/**
 * Resumes under their role, in the order each role first appears in `resumes`. A free-text role merges across
 * letter case and the first member's label is shown; a catalog role groups by its category. Resumes with no
 * role go in one last group (`label: null`), left out when empty. Members keep their order, archived or not.
 * `labelOf` supplies the display label, so this module never needs the role catalog.
 */
export function groupByRole<T extends RoleFields>(resumes: T[], labelOf: (resume: T) => string): RoleGroup<T>[] {
  const groups = new Map<string, RoleGroup<T>>();
  const unset: RoleGroup<T> = { key: "", label: null, resumes: [] };
  for (const resume of resumes) {
    if (isRoleUnset(resume)) {
      unset.resumes.push(resume);
      continue;
    }
    const key = resume.role_label ? `l:${resume.role_label.toLowerCase()}` : `c:${resume.role_category}`;
    const group = groups.get(key) ?? { key, label: labelOf(resume), resumes: [] };
    group.resumes.push(resume);
    groups.set(key, group);
  }
  return [...groups.values(), ...(unset.resumes.length > 0 ? [unset] : [])];
}
