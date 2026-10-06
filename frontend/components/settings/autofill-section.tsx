"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { useConfirm } from "@/components/confirm-dialog";
import { useFocusOnNextCommit } from "@/hooks/use-focus-return";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { SettingCard } from "@/components/settings/setting-card";
import {
  ACTION_ROW,
  GROUP_HEADING,
  RemoveButton,
} from "@/components/settings/setting-layout";
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
import { useFieldMessage } from "@/components/resume-editor/field";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import { emailWarning, linkWarning, phoneWarning } from "@/lib/field-checks";
import { formatAbsoluteDateTime } from "@/lib/format-date";
import { cn } from "@/lib/utils";
import type {
  AutofillOptions,
  EeoConsent,
  EeoConsentUpdate,
  KBProfileOut,
  SettingEnvelope,
} from "@/lib/types";

/** The policy whose wording the agreement confirm (setConsentFormsEnabled)
 *  describes. Bump it with CURRENT_POLICY_VERSION
 *  (backend/app/schemas/eeo_consent.py) whenever that wording changes; the
 *  server grants the agreement only under its current policy. */
const AGREEMENT_POLICY = "2";

type FieldDef = {
  key: string;
  label: string;
  optional?: boolean;
  type?: "text" | "select";
  boolean?: boolean;
  options?: { value: string; label: string }[];
  /** A format or a consequence, between the label and the control. Never an example value. */
  hint?: string;
  /** Shown only while another field of the group holds this value: [key, value].
   *  Changing that field away deletes this one (see `setField`). */
  when?: [string, string];
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

/** Sub-section heading inside a card, in the career history read view's style
 *  (`GROUP_HEADING`), so a form section and a content section look alike. The
 *  `w-full` keeps the row-level actions ("Fill from career history", "Decline the rest")
 *  pinned to the far end of the legend. */
const LEGEND = cn(GROUP_HEADING, "flex w-full items-center justify-between gap-2");

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
      { key: "address_2", label: "Address line 2", optional: true },
      { key: "city", label: "City" },
      { key: "state", label: "State" },
      { key: "postal_code", label: "Postal code" },
      { key: "country", label: "Country" },
      { key: "linkedin", label: "LinkedIn profile link" },
      { key: "github", label: "GitHub link" },
      { key: "website", label: "Website" },
    ],
  },
  {
    key: "work_auth",
    title: "Work authorization",
    fields: [
      {
        key: "status",
        label: "Work authorization status",
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
        label: "Do you need visa sponsorship now?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
      {
        key: "sponsorship_future",
        label: "Will you need visa sponsorship later?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
    ],
  },
  {
    key: "eeo",
    title: "Diversity questions (voluntary)",
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
        // The stored values are the Companion's (content/eeo.js maps each to
        // a form's own wording, and leaves a form without it to you).
        options: [
          { value: "male", label: "Male" },
          { value: "female", label: "Female" },
          { value: "non_binary", label: "Non-binary" },
          { value: "self_describe", label: "Prefer to self-describe" },
          { value: "decline", label: "Decline to answer" },
        ],
      },
      // Voluntary like the group, and not counted by setup readiness.
      {
        key: "gender_self_describe",
        label: "How you describe your gender",
        hint: "The Companion types this where a form asks you to self-describe.",
        optional: true,
        when: ["gender", "self_describe"],
      },
      {
        key: "hispanic_latino",
        label: "Hispanic or Latino?",
        type: "select",
        options: YES_NO_DECLINE,
      },
      // Optional for readiness (setup_status counts the other four); its
      // label carries no "(optional)", because the whole group is voluntary.
      {
        key: "race_ethnicity",
        label: "Race or ethnicity",
        optional: true,
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
        label: "Are you 18 or older?",
        type: "select",
        boolean: true,
        options: YES_NO,
        optional: true,
      },
      {
        key: "previously_employed_here",
        label: "Have you worked for the company you're applying to?",
        type: "select",
        boolean: true,
        options: YES_NO,
        optional: true,
      },
      {
        key: "non_compete",
        // The legal term stays in the label: forms ask it in those words and
        // the Companion matches them (shared/profile-fields.js). The hint says
        // what one is.
        label: "Subject to a restrictive covenant?",
        hint: "Such as a non-compete or non-solicit agreement.",
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
      { key: "desired_salary", label: "Desired salary" },
      { key: "notice_period", label: "Notice period", hint: "How long before you can start." },
      { key: "earliest_start_date", label: "Earliest start date" },
      {
        key: "willing_to_relocate",
        label: "Willing to relocate?",
        type: "select",
        boolean: true,
        options: YES_NO,
      },
      { key: "how_heard", label: "How did you hear about the job?" },
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
/** One language, stored as the fact catalog reads it
 *  (backend/app/services/autofill_catalog.py `_languages`). */
type LanguageEntry = {
  language?: string;
  read?: string;
  speak?: string;
  write?: string;
  native?: boolean;
  fluent?: boolean;
};
type Profile = {
  custom?: CustomQA[];
  education?: EducationEntry[] | EducationEntry;
  languages?: LanguageEntry[];
  [group: string]: unknown;
};

const EDUCATION_FIELDS: { key: keyof EducationEntry; label: string }[] = [
  { key: "school", label: "School" },
  { key: "degree", label: "Degree" },
  { key: "discipline", label: "Major" },
  { key: "gpa", label: "GPA" },
  { key: "start_year", label: "Start year" },
  { key: "end_year", label: "Graduation year" },
];

/** The levels in the words application forms offer, stored as those words. */
const LANGUAGE_LEVELS = ["Basic", "Intermediate", "Fluent"].map((level) => ({
  value: level,
  label: level,
}));
/** A language select's way back to no answer: the key is removed, never stored as "". */
const NOT_SET = { value: "not_set", label: "Not set" };

/** Native and fluent are separate answers: forms ask them apart. */
const LANGUAGE_FIELDS: FieldDef[] = [
  { key: "language", label: "Language" },
  { key: "read", label: "Reading", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "speak", label: "Speaking", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "write", label: "Writing", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "native", label: "Native speaker", type: "select", boolean: true, options: [NOT_SET, ...YES_NO] },
  { key: "fluent", label: "Fluent", type: "select", boolean: true, options: [NOT_SET, ...YES_NO] },
];

function withAnswer(
  entry: LanguageEntry,
  key: string,
  value: string | boolean | undefined,
): LanguageEntry {
  const next: Record<string, unknown> = { ...entry };
  if (value === undefined || value === "") delete next[key];
  else next[key] = value;
  return next as LanguageEntry;
}

/** What a language answer's control shows. A select is case-blind (a stored
 *  "fluent" shows as Fluent) and shows "Not set" rather than "Choose" when
 *  nothing, or nothing it offers, is stored. */
function languageValue(field: FieldDef, stored: unknown): string {
  const value = fieldValue(field, stored);
  if (field.type !== "select") return value;
  return field.options?.find((o) => o.value.toLowerCase() === value.toLowerCase())?.value || NOT_SET.value;
}

/** The input type, autofill token and format check of the contact fields forms read. */
const CONTACT_INPUT: Record<
  string,
  { type: "email" | "tel" | "url"; autoComplete: string; check: (v: string) => string | null }
> = {
  email: { type: "email", autoComplete: "email", check: (v) => emailWarning(v) },
  phone: { type: "tel", autoComplete: "tel", check: (v) => phoneWarning(v) },
  linkedin: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
  github: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
  website: { type: "url", autoComplete: "url", check: (v) => linkWarning(v) },
};

/** One answer's control: a select over its options, or a text box. `onChange`
 *  gets what to store; undefined ("Not set") removes the key. */
function FieldControl({
  id,
  group,
  field,
  value,
  hintId,
  onChange,
}: {
  id: string;
  group: string;
  field: FieldDef;
  value: string;
  hintId?: string;
  onChange: (next: string | boolean | undefined) => void;
}) {
  // A warning shows once the field is left, not on every keystroke, and never blocks a save.
  const [warning, setWarning] = useState<string | null>(null);
  const contact = field.type === "select" || group !== "personal" ? undefined : CONTACT_INPUT[field.key];
  const { control, message } = useFieldMessage({ warning, hintId });
  return field.type === "select" ? (
    <Select
      value={value}
      onValueChange={(v) => onChange(v === NOT_SET.value ? undefined : storedFieldValue(field, v))}
    >
      <SelectTrigger id={id} size="sm" className="w-full" aria-describedby={hintId}>
        <SelectValue placeholder="Choose">
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
    <>
      <Input
        id={id}
        className="h-8 text-body-medium"
        value={value}
        type={contact?.type}
        autoComplete={contact?.autoComplete}
        {...control}
        onChange={(e) => {
          setWarning(null);
          onChange(e.target.value);
        }}
        onBlur={() => setWarning(contact ? contact.check(value) : null)}
      />
      {message}
    </>
  );
}

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
      title="Answers for job forms"
      description="The Companion uses these to fill job applications."
      errorTitle="Couldn't load your form answers."
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
  // Bumped by every edit, so a save that lands can tell whether the user typed
  // while it was in flight (Persona's rule).
  const editRevision = useRef(0);
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
  const languages: LanguageEntry[] = Array.isArray(profile.languages) ? profile.languages : [];

  const updateProfile = (updater: (current: Profile) => Profile) => {
    editRevision.current += 1;
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
      // A field shown only for one answer goes with that answer: a
      // self-description must not stay stored under "Female", unseen.
      for (const field of GROUPS.find((g) => g.key === group)?.fields ?? []) {
        if (field.when?.[0] === key && field.when[1] !== value) delete values[field.key];
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

  const setLanguages = (next: LanguageEntry[]) => {
    setDirty(true);
    updateProfile((current) => ({ ...current, languages: next }));
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
    mutationFn: (value: EeoConsentUpdate) =>
      apiFetch<SettingEnvelope<EeoConsent>>("/api/settings/eeo-consent", {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "eeo-consent"], result);
      setConsent(result.value);
      setLastConsent(result.value);
      // No toast here: two switches share this mutation, so each call names
      // its own switch (a shared toast announced the diversity state when the
      // agreement-box switch moved).
    },
    onError: (err: Error) => toast.error(couldnt("save your consent", err)),
  });

  const setEeoConsentEnabled = async (enabled: boolean) => {
    if (enabled) {
      const acknowledged = await confirm({
        title: "Let the Companion answer the voluntary diversity questions?",
        description:
          "The Companion will fill race, ethnicity, gender, veteran and "
          + "disability questions using only your exact answers below. It never "
          + "guesses and never uses AI for these. Tax-credit questions stay "
          + "with you, and this doesn't cover signatures or legal statements. "
          + "You can turn this off anytime.",
        confirmLabel: "Allow",
        consent: true,
      });
      if (!acknowledged) return;
    }
    saveConsent.mutate(
      {
        enabled,
        consent_forms: consent.consent_forms,
        // The server stamps the acknowledgement time on a yes.
        acknowledged_at: enabled ? null : consent.acknowledged_at,
        policy_version: consent.policy_version,
      },
      {
        onSuccess: () =>
          toast.success(
            enabled
              ? "The Companion can now answer diversity questions"
              : "The Companion won't answer diversity questions",
          ),
      },
    );
  };

  /** The second permission in the same record: with it on, the extension's
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
   *  moves to the next page and never submits. */
  const setConsentFormsEnabled = async (consentForms: boolean) => {
    if (consentForms) {
      const acknowledged = await confirm({
        title: "Let the Companion fill agreements and signatures?",
        // Every family extension/shared/policy.js refuses without it.
        description:
          "With this on, the Companion can fill every field on an application "
          + "form, including terms, acknowledgements, certifications, "
          + "arbitration and waivers, signatures, initials and typed-name "
          + "attestations. It never moves to the next page and never submits. "
          + "Check every form before you submit it. You can turn this off "
          + "anytime.",
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
        toast.info("Nothing new to add");
        return;
      }

      setDirty(true);
      updateProfile((current) => ({
        ...current,
        personal: { ...groupValues(current, "personal"), ...additions },
      }));
      toast.success(`Filled ${count} ${count === 1 ? "field" : "fields"} from your career history`);
    } catch (err) {
      toast.error(couldnt("load your career history", err));
    } finally {
      setIsFillingFromResume(false);
    }
  };

  const save = useMutation({
    mutationFn: ({ value, revision }: { value: Profile; revision: number }) =>
      apiFetch<{ key: string; value: Profile }>("/api/settings/autofill", {
        method: "PUT",
        body: JSON.stringify({ value }),
      }).then((result) => ({ result, revision })),
    onSuccess: ({ result, revision }) => {
      qc.setQueryData(["settings", "autofill"], result);
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      // Clean only when nothing changed since the save was sent: the re-seed
      // above then adopts the server copy. An edit made meanwhile keeps the
      // form dirty, so it is neither overwritten nor left without a Save.
      if (editRevision.current === revision) setDirty(false);
      toast.success("Answers saved");
    },
    onError: (err: Error) => toast.error(couldnt("save your answers", err)),
  });
  // One PUT per gesture: a double click sent two, and two "saved" toasts.
  const saveOnce = useSingleFlight(save.mutate);
  useLeaveGuard(dirty);
  // A removed education or question row takes its focused Remove with it;
  // focus goes to the Add button below the list.
  const armFocus = useFocusOnNextCommit();
  const addEducationRef = useRef<HTMLButtonElement>(null);
  const addLanguageRef = useRef<HTMLButtonElement>(null);
  const addQuestionRef = useRef<HTMLButtonElement>(null);
  const fillHintId = useId();
  const declineHintId = useId();

  return (
    // Groups are divided by their headings and a wide gap, never by rules. Each
    // fieldset stays in block flow: a rendered <legend> is not a grid item, so
    // a grid gap would never separate it from the first field.
    <div className="grid gap-8">
      <CompanionPermissions
        consent={consent}
        pending={saveConsent.isPending}
        onChange={(next) => void setConsentFormsEnabled(next)}
      />
      {GROUPS.map((group) => {
        const contactReady = hasFillableContactDetails(kbProfile.data?.contact);
        const resumeDisabledReason = kbProfile.isLoading
          ? "Loading your career history…"
          : kbProfile.isError
            ? "Couldn't load your career history."
            : "Add your contact details to your career history first.";
        // It reads career history (GET /api/kb/profile), and says so.
        const resumeButton = (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            focusableWhenDisabled
            disabled={!contactReady || isFillingFromResume}
            aria-describedby={contactReady ? undefined : fillHintId}
            className="data-disabled:pointer-events-none data-disabled:opacity-50"
            onClick={fillFromResume}
          >
            {isFillingFromResume ? "Filling…" : "Fill from career history"}
          </Button>
        );

        return (
        <fieldset key={group.key} id={`autofill-${group.key}`} className="space-y-4">
          <legend className={LEGEND}>
            <span>{group.title}</span>
            {group.key === "eeo" && (
              <Button
                type="button"
                variant="ghost"
                size="xs"
                aria-describedby={declineHintId}
                onClick={declineAllEeo}
              >
                Decline the rest
              </Button>
            )}
            {group.key === "personal" && resumeButton}
          </legend>
          {/* A disabled button's reason is text, not a hover. */}
          {group.key === "personal" && !contactReady ? (
            <p id={fillHintId} className="text-muted-foreground text-body-small">
              {resumeDisabledReason}
            </p>
          ) : null}
          {group.key === "eeo" ? (
            <p id={declineHintId} className="text-muted-foreground text-body-small">
              Fills your blank diversity questions with “Decline to answer”. Select Save answers to keep it.
            </p>
          ) : null}
          {group.key === "eeo" && (
            // A permission, not a field. The accent and the heading are the
            // whole point: it sits among the answer inputs because it governs
            // exactly those answers, but granting a standing consent is a
            // different KIND of act from typing one in, and a row that looks
            // like every other row does not say so.
            <CardSection className="border-primary/40 grid gap-3 border-l-2 px-3 py-2.5">
              <p className="text-title-small">
                Permission
              </p>
              <div className="flex items-center justify-between gap-4">
                <div className="grid gap-1">
                  <Label htmlFor="eeo-standing-consent">
                    Let the Companion fill these answers
                  </Label>
                  <p className="text-muted-foreground text-body-small">
                    Uses only your exact answers below. Off by default. Tax-credit
                    questions are always yours to fill.
                  </p>
                </div>
                <Switch
                  id="eeo-standing-consent"
                  checked={consent.enabled}
                  disabled={saveConsent.isPending}
                  onCheckedChange={(next) => void setEeoConsentEnabled(next)}
                />
              </div>
              {consent.enabled ? <AgreedOn consent={consent} /> : null}
            </CardSection>
          )}
          {/* items-end: a label that wraps (the longer questions at 14px) would
              otherwise push its control below its neighbours'. */}
          <div className="grid items-end gap-4 @lg/setting:grid-cols-2 @3xl/setting:grid-cols-3">
            {group.fields.map((field) => {
              if (field.when && groupValues(profile, group.key)[field.when[0]] !== field.when[1]) {
                return null;
              }
              const id = `af-${group.key}-${field.key}`;
              const rawValue = groupValues(profile, group.key)[field.key];
              const value = fieldValue(field, rawValue);
              const hintId = field.hint ? `${id}-hint` : undefined;
              return (
                <div key={field.key} className="grid gap-1.5">
                  <Label htmlFor={id} optional={field.optional && group.key !== "eeo"}>
                    {field.label}
                  </Label>
                  {field.hint ? (
                    <p id={hintId} className="text-muted-foreground text-body-small">
                      {field.hint}
                    </p>
                  ) : null}
                  <FieldControl
                    id={id}
                    group={group.key}
                    field={field}
                    value={value}
                    hintId={hintId}
                    onChange={(next) => setField(group.key, field.key, next)}
                  />
                </div>
              );
            })}
          </div>
        </fieldset>
        );
      })}

      <fieldset className="space-y-4">
        <legend className={LEGEND}>Education</legend>
        <p className="text-muted-foreground text-body-small">
          Most recent first.
        </p>
        {education.map((entry, i) => (
          <CardSection key={i} className="flex items-start gap-2">
            <div className="grid flex-1 gap-4 @xl/setting:grid-cols-3">
              {EDUCATION_FIELDS.map((field) => {
                const id = `af-education-${i}-${field.key}`;
                return (
                  <div key={field.key} className="grid gap-1.5">
                    <Label htmlFor={id}>{field.label}</Label>
                    <Input
                      id={id}
                      className="h-8 text-body-medium"
                      value={entry[field.key] ?? ""}
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
            <RemoveButton
              label={`Remove school ${i + 1}`}
              onClick={() => {
                setEducation(education.filter((_, j) => j !== i));
                armFocus(addEducationRef);
              }}
            />
          </CardSection>
        ))}
        <Button
          ref={addEducationRef}
          variant="outline"
          size="sm"
          onClick={() => setEducation([...education, {}])}
        >
          <Plus className="size-4" />
          Add education
        </Button>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className={LEGEND}>Languages</legend>
        <p className="text-muted-foreground text-body-small">
          Most important first. The first four are used, and the Companion adds a
          language to a form only when its reading, speaking and writing levels are all set.
        </p>
        {languages.map((entry, i) => (
          <CardSection key={i} className="flex items-start gap-2">
            <div className="grid flex-1 items-end gap-4 @xl/setting:grid-cols-3">
              {LANGUAGE_FIELDS.map((field) => {
                const id = `af-languages-${i}-${field.key}`;
                return (
                  <div key={field.key} className="grid gap-1.5">
                    <Label htmlFor={id}>{field.label}</Label>
                    <FieldControl
                      id={id}
                      group="language"
                      field={field}
                      value={languageValue(field, entry[field.key as keyof LanguageEntry])}
                      onChange={(next) =>
                        setLanguages(
                          languages.map((entry2, j) =>
                            j === i ? withAnswer(entry2, field.key, next) : entry2,
                          ),
                        )
                      }
                    />
                  </div>
                );
              })}
            </div>
            <RemoveButton
              label={`Remove language ${i + 1}`}
              onClick={() => {
                setLanguages(languages.filter((_, j) => j !== i));
                armFocus(addLanguageRef);
              }}
            />
          </CardSection>
        ))}
        <Button
          ref={addLanguageRef}
          variant="outline"
          size="sm"
          onClick={() => setLanguages([...languages, {}])}
        >
          <Plus className="size-4" />
          Add language
        </Button>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className={LEGEND}>Your own questions</legend>
        <p className="text-muted-foreground text-body-small">
          Questions you get often, with your usual answers.
        </p>
        {custom.map((qa, i) => (
          <div key={i} className="flex items-start gap-2">
            <div className="grid flex-1 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor={`af-custom-${i}-question`}>Question</Label>
                <Input
                  id={`af-custom-${i}-question`}
                  className="h-8 text-body-medium"
                  aria-label={`Custom question ${i + 1}`}
                  value={qa.question}
                  onChange={(e) =>
                    setCustom(
                      custom.map((c, j) =>
                        j === i ? { ...c, question: e.target.value } : c,
                      ),
                    )
                  }
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`af-custom-${i}-answer`}>Answer</Label>
                <Textarea
                  id={`af-custom-${i}-answer`}
                  className="text-body-medium"
                  rows={2}
                  aria-label={`Answer to custom question ${i + 1}`}
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
            </div>
            <RemoveButton
              label={`Remove custom question ${i + 1}`}
              onClick={() => {
                setCustom(custom.filter((_, j) => j !== i));
                armFocus(addQuestionRef);
              }}
            />
          </div>
        ))}
        <Button
          ref={addQuestionRef}
          variant="outline"
          size="sm"
          onClick={() => setCustom([...custom, { question: "", answer: "" }])}
        >
          <Plus className="size-4" />
          Add question
        </Button>
      </fieldset>

      <div className={ACTION_ROW}>
        <Button
          focusableWhenDisabled
          disabled={save.isPending || !dirty}
          className="data-disabled:pointer-events-none data-disabled:opacity-50"
          onClick={() =>
            saveOnce({ value: profileRef.current, revision: editRevision.current })
          }
        >
          {save.isPending ? "Saving…" : "Save answers"}
        </Button>
      </div>
    </div>
  );
}

/** When the standing consent was given. One record holds both permissions, so both boxes read it. */
function AgreedOn({ consent }: { consent: EeoConsent }) {
  if (!consent.acknowledged_at) return null;
  return (
    <p className="text-muted-foreground text-body-small">
      You agreed on {formatAbsoluteDateTime(consent.acknowledged_at)}
      {consent.policy_version ? ` (policy ${consent.policy_version})` : ""}
    </p>
  );
}

/** The permission that covers every application form, not the diversity
 *  answers, so it heads the card in a box of its own. Stored beside the
 *  diversity opt-in (one consent record) but decided apart: disclosing
 *  protected characteristics and agreeing to an application's terms are not
 *  the same thing, and one switch for both would mean nobody could have the
 *  first without the second. */
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
    <CardSection className="border-primary/40 grid gap-3 border-l-2 px-3 py-2.5">
      <p className="text-title-small">
        Companion permissions
      </p>
      <div className="flex items-center justify-between gap-4">
        <div className="grid gap-1">
          <Label htmlFor="consent-forms">
            Let the Companion fill agreements and signatures
          </Label>
          <p id={hintId} className="text-muted-foreground text-body-small">
            The Companion can fill every field, including terms boxes,
            certifications, signatures and typed-name attestations. It never
            moves to the next page or submits.
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
      <LowStakesSwitch />
    </CardSection>
  );
}

/** Questions no answer of yours covers and whose answer barely matters, which
 *  the Companion answers in the job's favor while this is on (off by
 *  default). Its own setting, not the consent record: it is a preference,
 *  not a permission to disclose or agree. The server re-reads it on every
 *  fill (/map, /pick and /step), so this switch is the only way to turn it on. The
 *  kinds, and the never list, are the backend's (`_LOW_STAKES`,
 *  `_NEVER_LOW_STAKES` in backend/app/services/autofill_map.py). */
function LowStakesSwitch() {
  const qc = useQueryClient();
  const hintId = useId();
  const options = useQuery({
    queryKey: ["settings", "autofill-options"],
    queryFn: () => apiFetch<AutofillOptions>("/api/settings/autofill-options"),
  });
  const saveOptions = useMutation({
    mutationFn: (value: AutofillOptions) =>
      apiFetch<AutofillOptions>("/api/settings/autofill-options", {
        method: "PUT",
        body: JSON.stringify(value),
      }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "autofill-options"], result);
      toast.success(
        result.low_stakes
          ? "The Companion now answers low-stakes questions"
          : "The Companion won't answer low-stakes questions",
      );
    },
    onError: (err: Error) => toast.error(couldnt("save this setting", err)),
  });
  const saveOnce = useSingleFlight(saveOptions.mutate);
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="grid gap-1">
        <Label htmlFor="low-stakes">Answer low-stakes questions for me</Label>
        <div id={hintId} className="text-muted-foreground grid gap-1 text-body-small">
          <p>
            When none of your answers covers a question, the Companion answers
            it in the job&apos;s favor. It does this for:
          </p>
          <ul className="list-disc ps-4">
            <li>how you heard about the job and how to contact you</li>
            <li>whether you&apos;d relocate, travel, work on site, or work shifts or overtime</li>
            <li>whether you&apos;d take a drug test</li>
            <li>openness to other roles</li>
            <li>whether you&apos;re related to or used to work for the company</li>
            <li>what you would do if you become employed by the company</li>
            <li>consent to text and marketing messages</li>
            <li>whether you have the experience and education the job description asks for</li>
          </ul>
          <p>It lists them under Answered for you, so you can check each one.</p>
          <p>
            It never guesses your education and work history, work
            authorization, sponsorship, age, diversity questions, background
            checks, security clearance, salary, or signatures.
          </p>
          <p>
            Whether this is on or off, Fill may also answer some questions
            from your work history. These ask about past employment by a kind
            of organization (such as a government agency), a security clearance
            or years of experience. Fill lists those for you to check too.
          </p>
        </div>
        {options.isError ? (
          <p className="text-label-medium">Couldn&apos;t load this setting.</p>
        ) : null}
      </div>
      <Switch
        id="low-stakes"
        aria-describedby={hintId}
        checked={options.data?.low_stakes ?? false}
        disabled={!options.data}
        onCheckedChange={(low_stakes) => saveOnce({ low_stakes })}
      />
    </div>
  );
}
