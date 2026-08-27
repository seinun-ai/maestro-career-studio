"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { SettingCard } from "@/components/settings/setting-card";
import { Button } from "@/components/ui/button";
import { CardSection } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api";
import type { EeoConsent, KBProfileOut, SettingEnvelope } from "@/lib/types";

type FieldDef = {
  key: string;
  label: string;
  optional?: boolean;
  type?: "text" | "select";
  boolean?: boolean;
  options?: { value: string; label: string }[];
  placeholder?: string;
};

type GroupDef = { key: string; title: string; fields: FieldDef[] };


const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];
const YES_NO_DECLINE = [
  ...YES_NO,
  { value: "decline", label: "Decline to answer" },
];

/** Sub-section heading inside a card — same treatment the Career KB profile
 *  read view uses, so a form section and a content section look alike. The
 *  trailing `w-full` keeps the row-level actions ("Fill from resume",
 *  "Decline all") pinned to the far end of the legend. */
const LEGEND =
  "text-muted-foreground flex w-full items-center justify-between gap-2 text-xs font-semibold tracking-[0.12em] uppercase";

const GROUPS: GroupDef[] = [
  {
    key: "personal",
    title: "Personal details",
    fields: [
      { key: "first_name", label: "First name" },
      { key: "last_name", label: "Last name" },
      { key: "email", label: "Email" },
      { key: "phone", label: "Phone" },
      { key: "address", label: "Street address" },
      { key: "address_2", label: "Address line 2", optional: true, placeholder: "e.g. Apt 4B" },
      { key: "city", label: "City" },
      { key: "state", label: "State" },
      { key: "postal_code", label: "Postal code" },
      { key: "country", label: "Country" },
      { key: "linkedin", label: "LinkedIn URL" },
      { key: "github", label: "GitHub URL" },
      { key: "website", label: "Portfolio / website" },
    ],
  },
  {
    key: "work_auth",
    title: "Work authorization",
    fields: [
      {
        key: "status",
        label: "Current work authorization status",
        type: "select",
        options: [
          { value: "citizen", label: "U.S. citizen" },
          { value: "permanent_resident", label: "Permanent resident" },
          { value: "opt", label: "F-1 OPT" },
          { value: "stem_opt", label: "F-1 STEM OPT" },
          { value: "h1b", label: "H-1B" },
          { value: "tn", label: "TN" },
          { value: "other_visa", label: "Other visa or status" },
          { value: "not_authorized", label: "Not authorized to work in the U.S." },
        ],
      },
      {
        key: "authorized_now",
        label: "Authorized to work in the U.S. now?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
      {
        key: "sponsorship_now",
        label: "Do you require sponsorship now?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
      {
        key: "sponsorship_future",
        label: "Will you require sponsorship in the future?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
    ],
  },
  {
    key: "eeo",
    title: "Voluntary disclosures (EEO)",
    fields: [
      {
        key: "veteran_status",
        label: "Veteran status",
        type: "select",
        options: [
          { value: "not_veteran", label: "I am not a protected veteran" },
          { value: "veteran", label: "I identify as a veteran" },
          { value: "decline", label: "Decline to answer" },
        ],
      },
      {
        key: "disability_status",
        label: "Disability status",
        type: "select",
        options: [
          { value: "no", label: "No, I do not have a disability" },
          { value: "yes", label: "Yes, I have a disability" },
          { value: "decline", label: "Decline to answer" },
        ],
      },
      {
        key: "gender",
        label: "Gender",
        type: "select",
        options: [
          { value: "male", label: "Male" },
          { value: "female", label: "Female" },
          { value: "decline", label: "Decline to answer" },
        ],
      },
      {
        key: "hispanic_latino",
        label: "Hispanic or Latino?",
        type: "select",
        options: YES_NO_DECLINE,
      },
      {
        key: "race_ethnicity",
        label: "Race / ethnicity",
        optional: true,
        placeholder: "e.g. Asian",
      },
    ],
  },
  {
    key: "eligibility",
    title: "Eligibility",
    fields: [
      // The three questions nearly every US application asks and that nothing
      // else in this profile can derive. They are knockout answers, so each is
      // UNSET until you set it: an eligibility question the extension has no
      // answer for is reported and left blank, never guessed.
      //
      // "Previously employed here" is per-EMPLOYER by nature and stored as one
      // standing answer, which is the compromise it is worth naming: it is the
      // most common unanswered question in the telemetry (six hosts, worded
      // differently on every one), and "No" is the true answer at almost every
      // employer. Where it is not, it has to be changed by hand — hence the
      // wording of the label.
      {
        key: "over_18",
        label: "Are you 18 years of age or older?",
        type: "select",
        boolean: true,
        options: YES_NO,
        optional: true,
      },
      {
        key: "previously_employed_here",
        label: "Previously employed by the company you are applying to?",
        type: "select",
        boolean: true,
        options: YES_NO,
        optional: true,
      },
      {
        key: "non_compete",
        label: "Subject to a non-compete or restrictive covenant?",
        type: "select",
        boolean: true,
        options: YES_NO,
        optional: true,
      },
    ],
  },
  {
    key: "preferences",
    title: "Preferences",
    fields: [
      { key: "desired_salary", label: "Desired salary", placeholder: "e.g. $120,000" },
      { key: "notice_period", label: "Notice period", placeholder: "e.g. 2 weeks" },
      { key: "earliest_start_date", label: "Earliest start date" },
      {
        key: "willing_to_relocate",
        label: "Willing to relocate?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
      { key: "how_heard", label: "How did you hear about us?", placeholder: "e.g. Job board" },
    ],
  },
];

type CustomQA = { question: string; answer: string };
type EducationEntry = {
  school?: string;
  degree?: string;
  discipline?: string;
  gpa?: string;
  start_year?: string;
  end_year?: string;
};
type Profile = {
  custom?: CustomQA[];
  education?: EducationEntry[] | EducationEntry;
  [group: string]: unknown;
};

const EDUCATION_FIELDS: { key: keyof EducationEntry; label: string; placeholder?: string }[] = [
  { key: "school", label: "School / university" },
  { key: "degree", label: "Degree", placeholder: "e.g. Master of Science" },
  { key: "discipline", label: "Discipline / major", placeholder: "e.g. Data Science" },
  { key: "gpa", label: "GPA", placeholder: "e.g. 3.8" },
  { key: "start_year", label: "Start year", placeholder: "e.g. 2021" },
  { key: "end_year", label: "Graduation year", placeholder: "e.g. 2023" },
];

function educationList(profile: Profile): EducationEntry[] {
  const value = profile.education;
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return [value]; // legacy single entry
  return [];
}

function groupValues(profile: Profile, group: string): Record<string, unknown> {
  const value = profile[group];
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function isBlank(value: unknown): boolean {
  return typeof value !== "string" || !value.trim();
}

const TYPED_WORK_AUTH_KEYS = [
  "status",
  "authorized_now",
  "sponsorship_now",
  "sponsorship_future",
  "authorization_expires_on",
  "countries_authorized",
];

const BOOLEAN_WORK_AUTH_KEYS = [
  "authorized_now",
  "sponsorship_now",
  "sponsorship_future",
];

/** A yes/no answer from whatever is actually in the profile.
 *
 * THREE WRITERS reach these keys and they do not agree on a type, which is why
 * this is a coercion rather than a read: this form writes booleans, the profile
 * JSON is documented as hand-editable, and the extension's PAUSE ROW writes the
 * user's answer AS TYPED — "Yes", "yes", "No" — because the fill engine's
 * `yesNo` passes a string straight through and its option matcher lower-cases
 * before comparing.
 *
 * So the trimming and lower-casing here are load-bearing for a field that
 * declares `boolean: true`, and NOT declaring it is what made this a defect:
 * `fieldValue` then returns the raw string, "Yes" matches no `YES_NO` option
 * value, and the select renders EMPTY. The user opens Settings and the answer
 * they gave in the panel is simply not there — while the engine, which reads
 * the same profile, fills the field correctly. A value stored must render in
 * every reader, and this form is the reader the extension cannot test.
 */
function booleanAnswer(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  if (value.trim().toLowerCase() === "yes") return true;
  if (value.trim().toLowerCase() === "no") return false;
  return undefined;
}

function profileForEditing(profile: Profile): Profile {
  const raw = profile.work_auth;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return profile;

  const {
    authorized_to_work: legacyAuthorized,
    requires_sponsorship: legacySponsorship,
    ...workAuth
  } = raw as Record<string, unknown>;
  const hasTypedAnswer = TYPED_WORK_AUTH_KEYS.some((key) => key in workAuth);

  // The legacy sponsorship flag was never time-scoped. It can safely preserve
  // the future answer, but sponsorship_now and status must remain unanswered.
  if (!hasTypedAnswer) {
    const authorizedNow = booleanAnswer(legacyAuthorized);
    const sponsorshipFuture = booleanAnswer(legacySponsorship);
    if (authorizedNow !== undefined) workAuth.authorized_now = authorizedNow;
    if (sponsorshipFuture !== undefined) {
      workAuth.sponsorship_future = sponsorshipFuture;
    }
  }

  // Typed boolean answers may also have been hand-written as yes/no strings.
  // Normalize only known answers; an unusable value stays unknown to the UI.
  for (const key of BOOLEAN_WORK_AUTH_KEYS) {
    const answer = booleanAnswer(workAuth[key]);
    if (answer !== undefined) workAuth[key] = answer;
  }

  return { ...profile, work_auth: workAuth };
}

function fieldValue(field: FieldDef, value: unknown): string {
  if (field.boolean) {
    const answer = booleanAnswer(value);
    return answer === undefined ? "" : answer ? "yes" : "no";
  }
  return typeof value === "string" ? value : "";
}

function storedFieldValue(
  field: FieldDef,
  value: string | null,
): string | boolean | undefined {
  if (!field.boolean) return value ?? "";
  if (value === "yes") return true;
  if (value === "no") return false;
  return undefined;
}

type ContactLocation = {
  city: string;
  state: string;
  country?: string;
};

const PLACE_SEGMENT = /^[\p{L}][\p{L}\p{M} .'-]*$/u;
const STATE_ABBREVIATION = /^[A-Za-z]{2}$/;

function parseContactLocation(location: string | null | undefined): ContactLocation | null {
  if (typeof location !== "string") return null;

  const parts = location.split(",").map((part) => part.trim());
  if (parts.length !== 2 && parts.length !== 3) return null;

  const [city, state, country] = parts;
  if (
    !city ||
    !state ||
    !PLACE_SEGMENT.test(city) ||
    !STATE_ABBREVIATION.test(state) ||
    (parts.length === 3 && (!country || !PLACE_SEGMENT.test(country)))
  ) {
    return null;
  }

  return {
    city,
    state,
    ...(country ? { country } : {}),
  };
}

function resumeContactCandidates(
  contact: KBProfileOut["contact"] | undefined,
): Array<[key: string, value: string]> {
  const name = contact?.name?.trim() ?? "";
  const [firstName = "", ...lastNameParts] = name ? name.split(/\s+/) : [];
  const location = parseContactLocation(contact?.location);
  const candidates: Array<[string, string | null | undefined]> = [
    ["first_name", firstName],
    ["last_name", lastNameParts.join(" ")],
    ["email", contact?.email],
    ["phone", contact?.phone],
    ["linkedin", contact?.linkedin],
    ["github", contact?.github],
    ["website", contact?.website],
    ["city", location?.city],
    ["state", location?.state],
    ["country", location?.country],
  ];

  return candidates.flatMap(([key, value]) => {
    const normalized = value?.trim();
    return normalized ? [[key, normalized]] : [];
  });
}

function hasFillableContactDetails(
  contact: KBProfileOut["contact"] | undefined,
): boolean {
  return resumeContactCandidates(contact).length > 0;
}

export function AutofillSection() {
  const query = useQuery({
    queryKey: ["settings", "autofill"],
    queryFn: () =>
      apiFetch<SettingEnvelope<Profile>>("/api/settings/autofill"),
  });
  const consentQuery = useQuery({
    queryKey: ["settings", "eeo-consent"],
    queryFn: () =>
      apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent"),
  });

  return (
    <SettingCard
      id="autofill"
      title="Autofill profile"
      description="Preset answers the browser extension uses to fill job-application forms."
      errorTitle="Couldn't load your autofill profile."
      skeleton="h-40 w-full"
      query={query}
      // The consent record gates the EEO switches inside the editor, so the
      // body genuinely needs both responses before it can render.
      also={[consentQuery]}
    >
      {(data) => (
        <AutofillEditor
          initial={data.value}
          initialConsent={consentQuery.data!.value}
        />
      )}
    </SettingCard>
  );
}

function AutofillEditor({
  initial,
  initialConsent,
}: {
  initial: Profile;
  initialConsent: EeoConsent;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [profile, setProfile] = useState<Profile>(() => profileForEditing(initial));
  const profileRef = useRef<Profile>(profileForEditing(initial));
  const [dirty, setDirty] = useState(false);
  const [lastInitial, setLastInitial] = useState(initial);
  const [isFillingFromResume, setIsFillingFromResume] = useState(false);
  const [consent, setConsent] = useState<EeoConsent>(initialConsent);
  const [lastConsent, setLastConsent] = useState(initialConsent);
  const kbProfile = useQuery({
    queryKey: ["kb", "profile"],
    queryFn: () => apiFetch<KBProfileOut>("/api/kb/profile"),
  });

  // Re-seed if a background refetch delivers a different saved profile and the
  // user has no local edits in flight.
  if (!dirty && initial !== lastInitial) {
    const next = profileForEditing(initial);
    setLastInitial(initial);
    setProfile(next);
  }
  if (initialConsent !== lastConsent) {
    setLastConsent(initialConsent);
    setConsent(initialConsent);
  }

  useEffect(() => {
    profileRef.current = profile;
  }, [profile]);

  const custom: CustomQA[] = Array.isArray(profile.custom) ? profile.custom : [];
  const education = educationList(profile);

  const updateProfile = (updater: (current: Profile) => Profile) => {
    const next = updater(profileRef.current);
    profileRef.current = next;
    setProfile(next);
  };

  const setField = (
    group: string,
    key: string,
    value: string | boolean | undefined,
  ) => {
    setDirty(true);
    updateProfile((current) => {
      const values = { ...groupValues(current, group) };
      if (value === undefined) {
        delete values[key];
      } else {
        values[key] = value;
      }
      return { ...current, [group]: values };
    });
  };

  const setCustom = (next: CustomQA[]) => {
    setDirty(true);
    updateProfile((current) => ({ ...current, custom: next }));
  };

  const setEducation = (next: EducationEntry[]) => {
    setDirty(true);
    updateProfile((current) => ({ ...current, education: next }));
  };

  const declineAllEeo = () => {
    const eeo = groupValues(profileRef.current, "eeo");
    const eeoFields = GROUPS.find((group) => group.key === "eeo")?.fields ?? [];
    const declines = Object.fromEntries(
      eeoFields.flatMap((field) => {
        if (field.type !== "select" || !isBlank(eeo[field.key])) return [];
        const decline = field.options?.find((option) => option.label === "Decline to answer");
        return decline ? [[field.key, decline.value]] : [];
      }),
    );

    if (!Object.keys(declines).length) return;
    setDirty(true);
    updateProfile((current) => ({
      ...current,
      eeo: { ...groupValues(current, "eeo"), ...declines },
    }));
  };

  const saveConsent = useMutation({
    mutationFn: (value: EeoConsent) =>
      apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent", {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "eeo-consent"], result);
      setConsent(result.value);
      setLastConsent(result.value);
      toast.success(
        result.value.enabled
          ? "EEO standing consent enabled"
          : "EEO standing consent turned off",
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const setEeoConsentEnabled = async (enabled: boolean) => {
    if (enabled) {
      const acknowledged = await confirm({
        title: "Let autofill answer voluntary EEO questions?",
        description:
          "Maestro CS Companion will fill self-identification fields "
          + "(race/ethnicity, gender, veteran status, disability) using only the "
          + "exact answers stored below. Answers are never inferred or authored "
          + "by an AI. WOTC, signatures, and legal attestations stay manual. You "
          + "can turn this off anytime.",
        confirmLabel: "Allow EEO fill",
      });
      if (!acknowledged) return;
      saveConsent.mutate({
        enabled: true,
        consent_forms: consent.consent_forms,
        acknowledged_at: null, // server stamps acknowledgement time
        policy_version: consent.policy_version,
      });
      return;
    }
    saveConsent.mutate({
      enabled: false,
      consent_forms: consent.consent_forms,
      acknowledged_at: consent.acknowledged_at,
      policy_version: consent.policy_version,
    });
  };

  /** The second permission in the same record: may the extension tick the
   *  application's OWN agreement boxes — "Yes, I have read and consent to the
   *  terms and conditions" and its family.
   *
   *  Asked for separately from the EEO opt-in on purpose. They are one thing
   *  to the user — what may this fill answer for me — and two decisions, and
   *  folding them into one switch would make enabling EEO fill also enable
   *  agreeing to terms, which nobody chose.
   *
   *  What it does NOT unlock is in the confirm text, because it is the part
   *  worth knowing: signatures and initials stay manual (producing your name
   *  is an act, not an agreement), and passwords and government identifiers
   *  are never filled at any setting. */
  const setConsentFormsEnabled = async (consentForms: boolean) => {
    if (consentForms) {
      const acknowledged = await confirm({
        title: "Let autofill tick agreement boxes?",
        description:
          "This covers an application's own terms and conditions, "
          + "acknowledgements and attestations. It ticks a box; it never signs "
          + "and never submits. Signature and initials fields stay manual, and "
          + "passwords and government ID numbers are never filled whatever you "
          + "choose here. Review every form before you submit it. You can turn "
          + "this off anytime.",
        confirmLabel: "Allow ticking boxes",
      });
      if (!acknowledged) return;
    }
    saveConsent.mutate({
      enabled: consent.enabled,
      consent_forms: consentForms,
      acknowledged_at: consentForms ? null : consent.acknowledged_at,
      policy_version: consent.policy_version,
    });
  };

  const fillFromResume = async () => {
    setIsFillingFromResume(true);
    try {
      const { contact } = await apiFetch<KBProfileOut>("/api/kb/profile");
      const personal = groupValues(profileRef.current, "personal");
      const candidates = resumeContactCandidates(contact);
      const additions = Object.fromEntries(
        candidates.flatMap(([key, value]) =>
          isBlank(personal[key]) ? [[key, value]] : [],
        ),
      );
      const count = Object.keys(additions).length;

      if (!count) {
        toast.info("Nothing new to fill");
        return;
      }

      setDirty(true);
      updateProfile((current) => ({
        ...current,
        personal: { ...groupValues(current, "personal"), ...additions },
      }));
      toast.success(`Filled ${count} fields from your career profile`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not load your career profile");
    } finally {
      setIsFillingFromResume(false);
    }
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<{ key: string; value: Profile }>("/api/settings/autofill", {
        method: "PUT",
        body: JSON.stringify({ value: profile }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "autofill"], result);
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      setDirty(false);
      toast.success("Autofill profile saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    // Five groups ran together as one column of fields because a bare
    // `space-y-6` gap was all that separated them. Any fieldset that FOLLOWS
    // another gets a rule and a wider gap, so the boundaries hold for the
    // mapped groups and the three literal ones below without either side
    // having to know its own position.
    //
    // The rule goes on the LEGEND, not the fieldset. A <legend> is a "rendered
    // legend": the browser lays it over the fieldset's block-start border and
    // CLIPS the border behind it. These legends span the full width, so a
    // border-top on the fieldset was clipped along its whole length and simply
    // never appeared — it measured 1px and painted nothing.
    <div className="space-y-6 [&>fieldset~fieldset>legend]:border-t [&>fieldset~fieldset>legend]:pt-6">
      {GROUPS.map((group) => {
        const contactReady = hasFillableContactDetails(kbProfile.data?.contact);
        const resumeDisabledReason = kbProfile.isLoading
          ? "Loading your career profile…"
          : kbProfile.isError
            ? "Could not load your career profile."
            : "Add usable contact details to your career profile first.";
        const resumeButton = (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={!contactReady || isFillingFromResume}
            onClick={fillFromResume}
          >
            {isFillingFromResume ? "Filling…" : "Fill from resume"}
          </Button>
        );

        return (
        <fieldset key={group.key} id={`autofill-${group.key}`} className="space-y-3">
          <legend className={LEGEND}>
            <span>{group.title}</span>
            {group.key === "eeo" && (
              <Button type="button" variant="ghost" size="xs" onClick={declineAllEeo}>
                Decline all
              </Button>
            )}
            {group.key === "personal" &&
              (contactReady ? (
                resumeButton
              ) : (
                <Tooltip>
                  <TooltipTrigger render={<span className="inline-flex">{resumeButton}</span>} />
                  <TooltipContent>{resumeDisabledReason}</TooltipContent>
                </Tooltip>
              ))}
          </legend>
          {group.key === "eeo" && (
            // Two permissions, not two fields. The accent and the heading are
            // the whole point: these sit among the answer inputs because they
            // govern exactly those answers, but granting a standing consent is
            // a different KIND of act from typing one in, and a row that looks
            // like every other row does not say so.
            <CardSection className="border-primary/40 space-y-2 border-l-2 px-3 py-2.5">
              <p className="text-xs font-medium tracking-wide uppercase">
                Permissions
              </p>
              <div className="flex items-center justify-between gap-4">
                <div className="space-y-0.5">
                  <Label htmlFor="eeo-standing-consent" className="text-sm">
                    Allow extension to fill these answers
                  </Label>
                  <p className="text-muted-foreground text-xs">
                    Standing consent for exact-match autofill only. Off by default;
                    WOTC and signatures stay manual.
                  </p>
                </div>
                <Switch
                  id="eeo-standing-consent"
                  checked={consent.enabled}
                  disabled={saveConsent.isPending}
                  onCheckedChange={(next) => void setEeoConsentEnabled(next)}
                />
              </div>
              {/* The second permission, in the same card and on its own switch.
                  One pack to grant, two decisions to make: disclosing
                  protected characteristics and agreeing to an application's
                  terms are not the same thing, and one switch for both would
                  mean nobody could have the first without the second. */}
              <div className="flex items-center justify-between gap-4">
                <div className="space-y-0.5">
                  <Label htmlFor="consent-forms" className="text-sm">
                    Allow extension to tick agreement boxes
                  </Label>
                  <p className="text-muted-foreground text-xs">
                    Terms and conditions, acknowledgements and attestations. It
                    ticks a box; it never signs and never submits. Signatures,
                    passwords and government ID numbers are never filled.
                  </p>
                </div>
                <Switch
                  id="consent-forms"
                  checked={consent.consent_forms}
                  disabled={saveConsent.isPending}
                  onCheckedChange={(next) => void setConsentFormsEnabled(next)}
                />
              </div>
              {(consent.enabled || consent.consent_forms) && consent.acknowledged_at && (
                <p className="text-muted-foreground text-[11px]">
                  Acknowledged {new Date(consent.acknowledged_at).toLocaleString()}
                  {consent.policy_version ? ` · policy ${consent.policy_version}` : ""}
                </p>
              )}
            </CardSection>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.fields.map((field) => {
              const id = `af-${group.key}-${field.key}`;
              const rawValue = groupValues(profile, group.key)[field.key];
              const value = fieldValue(field, rawValue);
              return (
                <div key={field.key} className="grid gap-1.5">
                  <Label htmlFor={id} className="text-xs" optional={field.optional}>
                    {field.label}
                  </Label>
                  {field.type === "select" ? (
                    <Select
                      value={value}
                      onValueChange={(v) =>
                        setField(
                          group.key,
                          field.key,
                          storedFieldValue(field, v),
                        )
                      }
                    >
                      <SelectTrigger id={id} size="sm" className="w-full">
                        <SelectValue placeholder="—">
                          {field.options?.find((o) => o.value === value)?.label}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {field.options?.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={id}
                      className="h-8 text-sm"
                      value={value}
                      placeholder={field.placeholder}
                      onChange={(e) => setField(group.key, field.key, e.target.value)}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </fieldset>
        );
      })}

      <fieldset className="space-y-3">
        <legend className={LEGEND}>Education</legend>
        <p className="text-muted-foreground text-xs">
          Most recent first, matching the extension&apos;s repeated form blocks.
        </p>
        {education.map((entry, i) => (
          <CardSection key={i} className="flex items-start gap-2">
            <div className="grid flex-1 gap-3 sm:grid-cols-3">
              {EDUCATION_FIELDS.map((field) => {
                const id = `af-education-${i}-${field.key}`;
                return (
                  <div key={field.key} className="grid gap-1.5">
                    <Label htmlFor={id} className="text-xs">
                      {field.label}
                    </Label>
                    <Input
                      id={id}
                      className="h-8 text-sm"
                      value={entry[field.key] ?? ""}
                      placeholder={field.placeholder}
                      onChange={(e) =>
                        setEducation(
                          education.map((entry2, j) =>
                            j === i ? { ...entry2, [field.key]: e.target.value } : entry2,
                          ),
                        )
                      }
                    />
                  </div>
                );
              })}
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Remove education entry"
              onClick={() => setEducation(education.filter((_, j) => j !== i))}
            >
              <Trash2 className="size-4" />
            </Button>
          </CardSection>
        ))}
        <Button variant="outline" size="sm" onClick={() => setEducation([...education, {}])}>
          <Plus className="size-4" />
          Add education
        </Button>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className={LEGEND}>Custom questions</legend>
        <p className="text-muted-foreground text-xs">
          Recurring form questions with your standard answers (matched by
          question text).
        </p>
        {custom.map((qa, i) => (
          <div key={i} className="flex items-start gap-2">
            <div className="grid flex-1 gap-1.5">
              <Input
                className="h-8 text-sm"
                aria-label={`Custom question ${i + 1}`}
                placeholder="e.g. Why do you want to work here?"
                value={qa.question}
                onChange={(e) =>
                  setCustom(
                    custom.map((c, j) =>
                      j === i ? { ...c, question: e.target.value } : c,
                    ),
                  )
                }
              />
              <Textarea
                className="text-sm"
                rows={2}
                aria-label={`Answer to custom question ${i + 1}`}
                placeholder="Answer"
                value={qa.answer}
                onChange={(e) =>
                  setCustom(
                    custom.map((c, j) =>
                      j === i ? { ...c, answer: e.target.value } : c,
                    ),
                  )
                }
              />
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Remove custom question"
              onClick={() => setCustom(custom.filter((_, j) => j !== i))}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCustom([...custom, { question: "", answer: "" }])}
        >
          <Plus className="size-4" />
          Add question
        </Button>
      </fieldset>

      <div className="flex justify-end">
        <Button onClick={() => save.mutate()} disabled={save.isPending || !dirty}>
          {save.isPending ? "Saving…" : "Save autofill profile"}
        </Button>
      </div>
    </div>
  );
}
