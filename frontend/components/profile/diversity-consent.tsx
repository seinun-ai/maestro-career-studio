"use client";

import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { AgreedOn } from "@/components/settings/companion-fill-section";
import { CardSection } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSaveConsent } from "@/hooks/use-save-consent";
import { apiFetch } from "@/lib/api";
import type { EeoConsent, SettingEnvelope } from "@/lib/types";

/** The words a yes to the diversity permission is given under, in Profile and in Setup alike. */
export const DIVERSITY_CONSENT_CONFIRM = {
  title: "Let the Companion answer the voluntary diversity questions?",
  description:
    "The Companion will fill race, ethnicity, gender, veteran and disability questions using only your exact answers below. "
    + "It never guesses and never uses AI for these. "
    + "Tax-credit questions stay with you, and this doesn't cover signatures or legal statements. "
    + "You can turn this off anytime.",
  confirmLabel: "Allow",
  consent: true,
} as const;

export function useEeoConsentQuery() {
  return useQuery({
    queryKey: ["settings", "eeo-consent"],
    queryFn: () => apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent"),
  });
}

/**
 * The diversity permission (inv-eeo-standing-consent): `enabled` lets the Companion disclose your diversity
 * answers. A yes asks first, in `DIVERSITY_CONSENT_CONFIRM`'s words, and the server stamps when it was
 * given (`acknowledged_at` is sent empty on a yes). The record's other permission, agreements and
 * signatures, is Settings › Companion's (companion-fill-section.tsx) and is sent back as it is.
 * `setEeoConsentEnabled` resolves true once the server has recorded the change, so a caller can store
 * an answer only after the consent it needs is on record.
 */
export function useDiversityConsent(consent: EeoConsent | undefined) {
  const confirm = useConfirm();
  // The one record's save: it toasts only a failure, so the yes or no is said below.
  const saveConsent = useSaveConsent();

  const setEeoConsentEnabled = async (enabled: boolean): Promise<boolean> => {
    if (!consent) return false;
    if (enabled) {
      const acknowledged = await confirm(DIVERSITY_CONSENT_CONFIRM);
      if (!acknowledged) return false;
    }
    try {
      await saveConsent.mutateAsync({
        enabled,
        consent_forms: consent.consent_forms,
        // The server stamps the acknowledgement time on a yes.
        acknowledged_at: enabled ? null : consent.acknowledged_at,
        policy_version: consent.policy_version,
      });
    } catch {
      return false; // said by onError's toast
    }
    toast.success(
      enabled
        ? "The Companion can now answer diversity questions"
        : "The Companion won't answer diversity questions",
    );
    return true;
  };

  return { pending: saveConsent.isPending, setEeoConsentEnabled };
}

/**
 * The switch beside the answers it covers (owner decision D10), with the date the yes was given.
 *
 * A permission, not a field. The accent and the heading are the whole point: it sits among the answer
 * inputs because it governs exactly those answers, but granting a standing consent is a different KIND
 * of act from typing one in, and a row that looks like every other row does not say so.
 */
export function DiversityConsentSwitch({
  consent,
  pending,
  onChange,
}: {
  consent: EeoConsent;
  pending: boolean;
  onChange: (enabled: boolean) => void;
}) {
  const hintId = useId();
  return (
    <CardSection className="border-primary/40 grid gap-3 border-l-2 px-3 py-2.5">
      <p className="text-title-small">
        Permission
      </p>
      <div className="flex items-center justify-between gap-4">
        <div className="grid gap-1">
          <Label htmlFor="eeo-standing-consent">
            Let the Companion fill these answers
          </Label>
          <p id={hintId} className="text-muted-foreground text-body-small">
            Uses only your exact answers below. Off by default. Tax-credit
            questions are always yours to fill.
          </p>
        </div>
        <Switch
          id="eeo-standing-consent"
          aria-describedby={hintId}
          checked={consent.enabled}
          disabled={pending}
          onCheckedChange={(next) => onChange(next)}
        />
      </div>
      {consent.enabled ? <AgreedOn consent={consent} /> : null}
    </CardSection>
  );
}
