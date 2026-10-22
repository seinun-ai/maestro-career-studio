"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { EeoConsent, EeoConsentUpdate, SettingEnvelope } from "@/lib/types";

/** The consent record's read (`GET /api/settings/eeo-consent`). */
export const CONSENT_KEY = ["settings", "eeo-consent"] as const;

/**
 * `PUT /api/settings/eeo-consent`. One record holds both permissions: Settings › Companion's agreements and
 * signatures switch (companion-fill-section.tsx) and Profile's diversity switch (diversity-consent.tsx), and
 * a write sends the other one back as served. No toast on a save: each caller names its own switch (a shared
 * toast once announced the diversity state when the agreement switch moved). A failure toasts.
 */
export function useSaveConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (value: EeoConsentUpdate) =>
      apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent", {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => qc.setQueryData(CONSENT_KEY, result),
    onError: (err: Error) => toast.error(couldnt("save your consent", err)),
  });
}
