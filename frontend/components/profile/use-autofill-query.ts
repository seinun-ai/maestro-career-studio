"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Profile } from "@/lib/autofill-options";
import type { SettingEnvelope } from "@/lib/types";

/** The answers for job forms as the server holds them (`GET /api/settings/autofill`). Profile's editors
 *  change the copy `AutofillProfileProvider` holds; their cards read this for loading and failure. */
export function useAutofillQuery() {
  return useQuery({
    queryKey: ["settings", "autofill"],
    queryFn: () => apiFetch<SettingEnvelope<Profile>>("/api/settings/autofill"),
  });
}
