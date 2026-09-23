"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { baseResumeLabel, type BaseResumeSummary } from "@/lib/types";

/** The base-resume list's cache key. An object, not a boolean or a string, so it
 *  can never collide with the `["base-resumes", slug]` detail key; every
 *  mutation's `["base-resumes"]` prefix invalidation still reaches it. */
export function baseResumesKey(includeArchived: boolean) {
  return ["base-resumes", { includeArchived }] as const;
}

/** The selectable list, or the same list with archived rows. One query for the
 *  grid, the score panel, chat's pin picker, and the two port dialogs. */
export function useBaseResumes(includeArchived = false) {
  return useQuery({
    queryKey: baseResumesKey(includeArchived),
    queryFn: () =>
      apiFetch<BaseResumeSummary[]>(
        includeArchived
          ? "/api/base-resumes?include_archived=true"
          : "/api/base-resumes",
      ),
  });
}

/** slug -> the resume's own name. Archived rows included: an application,
 *  score or proposal keeps pointing at a resume after it is archived. While the
 *  list loads, after it fails, or for a slug it lacks, `humanizeSlug` stands in
 *  (the `useRoleLabel` pattern). */
export function useBaseResumeLabel() {
  const { data } = useBaseResumes(true);
  return useCallback((slug: string) => baseResumeLabel(slug, data), [data]);
}
