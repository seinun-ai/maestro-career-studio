"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { QuestionSet } from "@/lib/types";

/**
 * The form questions for where you live and apply (`GET /api/settings/autofill/questions`): the one list Profile
 * and Setup ask from, resolved by the backend from its catalog. Not under the profile's `["settings", "autofill"]`
 * key: a market save invalidates both, and a nested key would read twice.
 */
export const formQuestionsQuery = queryOptions({
  queryKey: ["settings", "form-questions"],
  queryFn: () => apiFetch<QuestionSet>("/api/settings/autofill/questions"),
});

/** `formQuestionsQuery` read in a component. */
export function useFormQuestions() {
  return useQuery(formQuestionsQuery);
}
