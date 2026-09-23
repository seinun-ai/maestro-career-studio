"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import {
  baseResumeLabel,
  type BaseResumeDetail,
  type BaseResumeSummary,
} from "@/lib/types";

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

/** One résumé's name, for a surface that names a single slug which may be
 *  soft-deleted (chat cards, a proposal's pill, an application's details).
 *  The archived-inclusive list first; a slug that list lacks reads its own
 *  row (`["base-resumes", slug]`, the key the studios and chat's edit card
 *  use), which outlives a soft delete. That fetch runs only once the list has
 *  loaded without the slug, and only while `enabled`. `humanizeSlug` stands in
 *  while either loads, after a failure, or for a slug no row has. */
export function useBaseResumeName(slug: string, enabled = true) {
  const list = useBaseResumes(true);
  const listed = list.data?.find((r) => r.slug === slug);
  const row = useQuery({
    queryKey: ["base-resumes", slug],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${slug}`),
    enabled: enabled && list.isSuccess && !listed,
    retry: false,
  });
  const known = listed ?? row.data;
  return baseResumeLabel(slug, known ? [known] : null);
}
