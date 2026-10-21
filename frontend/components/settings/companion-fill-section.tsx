"use client";

import { useId } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { SettingCard } from "@/components/settings/setting-card";
import { Label } from "@/components/ui/label";
import { RadioGroup, Radio } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import { inOrder } from "@/lib/in-order";
import type {
  AutofillOptions,
  EeoConsent,
  EeoConsentUpdate,
  SettingEnvelope,
} from "@/lib/types";

/** The policy whose wording the agreement confirm (setConsentFormsEnabled)
 *  describes. Bump it with CURRENT_POLICY_VERSION
 *  (backend/app/schemas/eeo_consent.py) whenever that wording changes; the
 *  server grants the agreement only under its current policy. */
const AGREEMENT_POLICY = "2";

const CONSENT_KEY = ["settings", "eeo-consent"] as const;

/**
 * Settings › Companion: what the Companion may fill (owner decision D10). The agreements and signatures
 * permission, with the date you agreed, then how far it answers screening questions. The diversity
 * permission stays in Profile beside the answers it covers. Every consent rule is the server's: it
 * stamps the time, grants `consent_forms` only under its current policy, and serves an older yes off.
 */
export function CompanionFillSection() {
  const consent = useQuery({
    queryKey: CONSENT_KEY,
    queryFn: () => apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent"),
  });
  return (
    <SettingCard
      id="companion-fill"
      title="What the Companion may fill"
      errorTitle="Couldn't load what the Companion may fill."
      skeleton="h-40 w-full"
      query={consent}
    >
      {(data) => <CompanionFillEditor consent={data.value} />}
    </SettingCard>
  );
}

function CompanionFillEditor({ consent }: { consent: EeoConsent }) {
  const qc = useQueryClient();
  const confirm = useConfirm();

  // The record holds the diversity permission too (Profile's switch): a write sends it back as served.
  const saveConsent = useMutation({
    mutationFn: (value: EeoConsentUpdate) =>
      apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent", {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => qc.setQueryData(CONSENT_KEY, result),
    onError: (err: Error) => toast.error(couldnt("save your consent", err)),
  });

  /** The second permission in the record: with it on, the extension's
   *  label policy (extension/shared/policy.js) refuses nothing, so a fill may
   *  complete every field — the application's own agreement boxes, and also
   *  signatures, initials and typed-name attestations (owner's decision,
   *  2026-09-26).
   *
   *  Asked for separately from the EEO opt-in on purpose. They are one thing
   *  to the user — what may this fill answer for me — and two decisions, and
   *  folding them into one switch would make enabling EEO fill also enable
   *  agreeing to terms, which nobody chose.
   *
   *  What it never does, at any setting, is in the confirm text: it never
   *  submits, and it moves to the next page only during a queued run. */
  const setConsentFormsEnabled = async (consentForms: boolean) => {
    if (consentForms) {
      const acknowledged = await confirm({
        title: "Let the Companion fill agreements and signatures?",
        // Every family extension/shared/policy.js refuses without it.
        description:
          "With this on, the Companion can fill every field on an application "
          + "form, including terms, acknowledgements, certifications, "
          + "arbitration and waivers, signatures, initials and typed-name "
          + "attestations. It never submits. Only during a run of your queued "
          + "jobs does it move to the next page. Check every form before you "
          + "submit it. You can turn this off anytime.",
        confirmLabel: "Allow",
        consent: true,
      });
      if (!acknowledged) return;
    }
    saveConsent.mutate(
      {
        enabled: consent.enabled,
        consent_forms: consentForms,
        acknowledged_at: consentForms ? null : consent.acknowledged_at,
        policy_version: consent.policy_version,
        // The policy the confirm above describes; the server grants nothing else.
        agreed_policy: consentForms ? AGREEMENT_POLICY : undefined,
      },
      {
        // The server may hold a yes off (it names an older policy than the
        // server's), so the toast reads the saved value, not the request.
        onSuccess: (result) => {
          if (!consentForms) {
            toast.success("The Companion won't fill agreements and signatures");
          } else if (result.value.consent_forms) {
            toast.success("The Companion can now fill agreements and signatures");
          } else {
            toast.warning(
              "Agreements and signatures weren't turned on. Reload the page and try again.",
            );
          }
        },
      },
    );
  };

  return (
    <div className="grid gap-6">
      <CompanionPermissions
        consent={consent}
        pending={saveConsent.isPending}
        onChange={(next) => void setConsentFormsEnabled(next)}
      />
      <ScreeningAnswers />
    </div>
  );
}

/** When the standing consent was given. One record holds both permissions, so both boxes read it. */
export function AgreedOn({ consent }: { consent: EeoConsent }) {
  if (!consent.acknowledged_at) return null;
  return (
    <p className="text-muted-foreground text-body-small">
      You agreed on {formatAbsoluteDateTime(consent.acknowledged_at)}
      {consent.policy_version ? ` (policy ${consent.policy_version})` : ""}
    </p>
  );
}

/** The permission that covers every application form, not the diversity
 *  answers, so it lives here and not beside them in Profile (owner decision
 *  D10). Stored beside the diversity opt-in (one consent record) but decided
 *  apart: disclosing protected characteristics and agreeing to an
 *  application's terms are not the same thing, and one switch for both would
 *  mean nobody could have the first without the second. */
function CompanionPermissions({
  consent,
  pending,
  onChange,
}: {
  consent: EeoConsent;
  pending: boolean;
  onChange: (consentForms: boolean) => void;
}) {
  const hintId = useId();
  const lapsedId = useId();
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-4">
        <div className="grid gap-1">
          <Label htmlFor="consent-forms">
            Let the Companion fill agreements and signatures
          </Label>
          <p id={hintId} className="text-muted-foreground text-body-small">
            The Companion can fill every field, including terms boxes,
            certifications, signatures and typed-name attestations. It never
            submits. Only during a run of your queued jobs does it move to the
            next page.
          </p>
          {/* An agreement given under an older, narrower policy is served
              off (consent_forms_lapsed); a yes now records the current one. */}
          {consent.consent_forms_lapsed ? (
            <p id={lapsedId} className="text-label-medium">
              This now covers more than when you agreed. Turn it on again to
              allow it.
            </p>
          ) : null}
        </div>
        <Switch
          id="consent-forms"
          aria-describedby={
            consent.consent_forms_lapsed ? `${hintId} ${lapsedId}` : hintId
          }
          checked={consent.consent_forms}
          disabled={pending}
          onCheckedChange={onChange}
        />
      </div>
      {consent.consent_forms ? <AgreedOn consent={consent} /> : null}
    </div>
  );
}

/** How far the Companion answers screening questions no saved answer covers.
 *  Its own setting, not the consent record: it is a preference, not a
 *  permission to disclose or agree. The server re-reads it on every fill
 *  (/map, /pick and /step), so this dial is the only way to move it. What each
 *  level adds, and the protected list that no level moves, are the backend's
 *  (`answer_level` in backend/app/services/autofill_map.py). Saves go through
 *  `inOrder`, never a mutation `scope`: a scoped mutation queues as paused in
 *  a hidden tab and never runs (SYSTEM.md section 12). */
const ANSWER_LEVELS: {
  value: AutofillOptions["answer_level"];
  label: string;
  line: string;
  /** What a word in the line means, said once under it. */
  note?: string;
}[] = [
  {
    value: "facts",
    label: "Careful",
    line: "Only your saved answers and career history. Anything else waits for you.",
  },
  {
    value: "history",
    label: "Balanced",
    line:
      "Also answers low-stakes questions in the job's favor, and "
      + "years-with-a-skill questions when your history shows the skill.",
    note:
      "Low-stakes means how you heard about the job, travel, relocation and "
      + "similar. They show under Answered for you.",
  },
  {
    value: "queued",
    label: "Confident",
    line:
      "On jobs you queued, also answers Yes to requirement and years "
      + "questions. If your history shows fewer years, it asks you.",
  },
];

function ScreeningAnswers() {
  const qc = useQueryClient();
  const labelId = useId();
  const hintId = useId();
  const optionId = useId();
  const options = useQuery({
    queryKey: ["settings", "autofill-options"],
    queryFn: () => apiFetch<AutofillOptions>("/api/settings/autofill-options"),
  });
  const saveOptions = useMutation({
    mutationFn: (value: AutofillOptions) =>
      inOrder("autofill-options", () =>
        apiFetch<AutofillOptions>("/api/settings/autofill-options", {
          method: "PUT",
          body: JSON.stringify(value),
        }),
      ),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "autofill-options"], result);
      const picked = ANSWER_LEVELS.find((l) => l.value === result.answer_level);
      toast.success(`Screening answers: ${picked?.label ?? result.answer_level}`);
    },
    onError: (err: Error) => toast.error(couldnt("save this setting", err)),
  });
  // The pick shows at once and the saved value replaces it, so a second pick
  // made while the first saves is neither dropped nor shown as the old level.
  const shown = saveOptions.isPending
    ? saveOptions.variables.answer_level
    : options.data?.answer_level;
  return (
    <div className="grid gap-2">
      <Label id={labelId}>Screening answers</Label>
      <RadioGroup<AutofillOptions["answer_level"] | "">
        aria-labelledby={labelId}
        aria-describedby={hintId}
        value={shown ?? ""}
        disabled={!options.data}
        onValueChange={(answer_level) =>
          answer_level && saveOptions.mutate({ answer_level })
        }
      >
        {ANSWER_LEVELS.map((level) => (
          // The radio is named by its label alone and described by the lines
          // under it, so a screen reader doesn't read the whole paragraph as
          // the name.
          <label key={level.value} className="flex items-start gap-2">
            <Radio
              value={level.value}
              aria-labelledby={`${optionId}-${level.value}-label`}
              aria-describedby={`${optionId}-${level.value}-lines`}
            />
            <span className="grid gap-0.5">
              <span
                id={`${optionId}-${level.value}-label`}
                className="text-label-large"
              >
                {level.label}
              </span>
              <span
                id={`${optionId}-${level.value}-lines`}
                className="text-muted-foreground grid gap-0.5 text-body-small"
              >
                <span>{level.line}</span>
                {level.note ? <span>{level.note}</span> : null}
              </span>
            </span>
          </label>
        ))}
      </RadioGroup>
      <p id={hintId} className="text-muted-foreground text-body-small">
        Work authorization, sponsorship, salary, EEO, background, clearance and
        legal statements always wait for a saved answer, unless you allow
        agreements and signatures above.
      </p>
      {options.isError ? (
        <p className="text-label-medium">Couldn&apos;t load this setting.</p>
      ) : null}
    </div>
  );
}
