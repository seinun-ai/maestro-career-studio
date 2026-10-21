"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Profile } from "@/lib/autofill-options";
import type { SettingEnvelope } from "@/lib/types";

/**
 * The answers for job forms as the server holds them (`GET /api/settings/autofill`), for every page that edits
 * them (Profile, Setup's form answers). The Companion's pause row learns answers into this profile from another
 * window, and those pages save the WHOLE profile, so one that kept its old copy would erase a learned answer on
 * its next edit. Coming back to the tab reads again, `"always"` and not `true`: a learn made within the 30 s a
 * read stays fresh (app/providers.tsx) would otherwise be skipped. The editor takes the new copy only while
 * every edit is on the server (`useAutosave`'s `adopt`).
 */
export const autofillQuery = queryOptions({
  queryKey: ["settings", "autofill"],
  queryFn: () => apiFetch<SettingEnvelope<Profile>>("/api/settings/autofill"),
  refetchOnWindowFocus: "always",
});

/** `autofillQuery` read in a component: Profile's editors read it for loading and failure, and the copy
 *  `AutofillProfileProvider` holds is what they change. */
export function useAutofillQuery() {
  return useQuery(autofillQuery);
}
