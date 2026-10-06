"use client";

import { displayRoleTag, useRoleCategories } from "@/components/role-category-picker";
import { Badge } from "@/components/ui/badge";
import { countryName } from "@/lib/place-name";
import type { BaseResumeSummary } from "@/lib/types";

const ITEM_CLASS = "flex min-w-0 max-w-full";
const PILL_CLASS = "max-w-48 min-w-0";

/**
 * What a base resume's Target sets, as small pills: its country codes, role, company and focus.
 * Nothing renders when none is set. An unset role is not a pill: the gallery's own badge invites
 * one.
 */
export function AnchorPills({ resume }: { resume: BaseResumeSummary }) {
  const { data: options } = useRoleCategories();
  const roleSet = !(resume.role_category === "unknown" && !resume.role_label);
  const texts = [
    roleSet ? displayRoleTag(resume.role_category, resume.role_label, options) : null,
    resume.company,
    resume.focus,
  ].filter((text): text is string => Boolean(text));
  if (resume.countries.length === 0 && texts.length === 0) return null;
  return (
    <ul aria-label="Target" className="flex min-w-0 flex-wrap items-center gap-1">
      {resume.countries.map((code) => (
        <li key={code} className={ITEM_CLASS}>
          {/* The code fits a pill; its name is for the pointer and the screen reader. */}
          <Badge variant="secondary" className={PILL_CLASS} title={countryName(code)}>
            <span aria-hidden="true">{code}</span>
            <span className="sr-only">{countryName(code)}</span>
          </Badge>
        </li>
      ))}
      {texts.map((text, i) => (
        <li key={i} className={ITEM_CLASS}>
          {/* User text: capped and truncated, whole in `title`. */}
          <Badge variant="secondary" className={PILL_CLASS} title={text}>
            <span className="truncate">{text}</span>
          </Badge>
        </li>
      ))}
    </ul>
  );
}
