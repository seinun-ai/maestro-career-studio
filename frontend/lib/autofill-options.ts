/**
 * The autofill profile's questions, their options and how a stored answer reads, shared by Profile
 * (`components/profile/*`) and Setup (`components/setup/*`). Pure, so `node --test` loads it
 * (lib/autofill-options.test.ts): it imports only types, which the loader erases.
 *
 * `GROUPS` and `WORK_PERMIT_QUESTIONS` are a hand-mirror of `backend/app/services/setup_status.py`'s
 * required lists (`_PERSONAL`, `_EEO`, `_PREFERENCES`, `_WORK_AUTH_CORE`, `_US_VISA_CORE`): a field that
 * is not `optional` counts toward readiness. `backend/tests/test_autofill_groups_parity.py` fails when
 * the two drift.
 */

export type FieldDef = {
  key: string;
  label: string;
  optional?: boolean;
  type?: "text" | "select" | "date";
  boolean?: boolean;
  options?: { value: string; label: string }[];
  /** A format or a consequence, between the label and the control. Never an example value. */
  hint?: string;
  /** Instead of `hint` while the question is empty because the saved answer was dropped when the
   *  question changed (the backend lists it in the profile's `stale_answers`). */
  staleHint?: string;
  /** Shown only while another field of the group holds this value: [key, value].
   *  Changing that field away deletes this one (`withField`). */
  when?: [string, string];
};

export type GroupDef = { key: string; title: string; fields: FieldDef[] };

export const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];
export const YES_NO_DECLINE = [
  ...YES_NO,
  { value: "decline", label: "Decline to answer" },
];

/** How many saved answers a fill reads: `MAX_CUSTOM` in backend/app/services/autofill_catalog.py. */
export const CUSTOM_IN_USE = 30;

export const GROUPS: GroupDef[] = [
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
    key: "eeo",
    title: "Diversity questions (voluntary)",
    fields: [
      {
        key: "veteran_status",
        label: "Are you a veteran?",
        staleHint: "Answer again: this question changed.",
        type: "select",
        // One Yes/No. A "No" also answers a form's "not a protected veteran" option; a "Yes" alone never
        // says which protected class applies, so the Companion leaves that list to you. The backend
        // reads the old stored `veteran` as yes; the old `not_veteran` ("not a protected veteran")
        // is no answer to this question, so it is asked again (staleHint).
        options: [
          { value: "no", label: "No, I am not a veteran" },
          { value: "yes", label: "Yes, I am a veteran" },
          { value: "decline", label: "I don't wish to answer" },
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
      // employer. Where it is not, it has to be changed by hand, hence the
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

/** One group's fields, by key ("personal", "eeo", "eligibility", "preferences"). */
export function groupFields(key: string): FieldDef[] {
  return GROUPS.find((group) => group.key === key)?.fields ?? [];
}

// ------------------------------------------------------------------ Work permits, per country

/** A market's work-permit wording (`work_auth_vocab` in backend/app/services/data/markets.yaml, served on
 *  `GET /api/settings/market`). An unknown one reads as `generic`. */
export type WorkAuthVocab = "us_visa" | "uk" | "generic";

export type PermitKey = "status" | "authorized_now" | "sponsorship_now" | "sponsorship_future";

type PermitQuestion = { key: PermitKey; label: string };

/** The US visa statuses (`schemas/autofill_profile.py` WorkAuthStatus). Only a `us_visa` market asks it. */
export const US_WORK_STATUS = [
  { value: "citizen", label: "U.S. citizen" },
  { value: "permanent_resident", label: "Permanent resident" },
  { value: "opt", label: "F-1 OPT" },
  { value: "stem_opt", label: "F-1 STEM OPT" },
  { value: "h1b", label: "H-1B" },
  { value: "tn", label: "TN" },
  { value: "other_visa", label: "Other visa or status" },
  { value: "not_authorized", label: "Not authorized to work in the U.S." },
];

/**
 * The knockout answers each country asks, in its own words. Every country asks the three yes/no keys; the
 * visa status list is the US taxonomy, so only `us_visa` asks it. A country's set is shown under its name,
 * so the generic words say "this country" rather than guess at a name's grammar.
 */
const WORK_PERMIT_QUESTIONS: Record<WorkAuthVocab, PermitQuestion[]> = {
  us_visa: [
    { key: "status", label: "Work authorization status" },
    { key: "authorized_now", label: "Authorized to work in the U.S. now?" },
    { key: "sponsorship_now", label: "Do you need visa sponsorship now?" },
    { key: "sponsorship_future", label: "Will you need visa sponsorship later?" },
  ],
  uk: [
    { key: "authorized_now", label: "Do you have the right to work in the UK now?" },
    { key: "sponsorship_now", label: "Do you need visa sponsorship to work in the UK now?" },
    { key: "sponsorship_future", label: "Will you need visa sponsorship in the UK later?" },
  ],
  generic: [
    { key: "authorized_now", label: "Can you work in this country now?" },
    { key: "sponsorship_now", label: "Do you need visa sponsorship now?" },
    { key: "sponsorship_future", label: "Will you need visa sponsorship later?" },
  ],
};

export function permitVocab(vocab: string | null | undefined): WorkAuthVocab {
  return vocab === "us_visa" || vocab === "uk" ? vocab : "generic";
}

/** The required work-permit questions of one vocabulary, as fields (the status a select, the rest Yes/No). */
export function permitQuestions(vocab: string | null | undefined): FieldDef[] {
  return WORK_PERMIT_QUESTIONS[permitVocab(vocab)].map(({ key, label }) =>
    key === "status"
      ? { key, label, type: "select" as const, options: US_WORK_STATUS }
      : { key, label, type: "select" as const, boolean: true, options: YES_NO },
  );
}

/** One country's work-permit fields: its required questions, then when the permit runs out (optional). */
export function workPermitFields(vocab: string | null | undefined): FieldDef[] {
  return [
    ...permitQuestions(vocab),
    {
      key: "authorization_expires_on",
      label: "Authorization expires on",
      hint: "Leave it empty if your right to work there does not run out.",
      type: "date",
      optional: true,
    },
  ];
}

// ------------------------------------------------------------------------- Education and languages

export type EducationEntry = {
  school?: string;
  degree?: string;
  discipline?: string;
  gpa?: string;
  start_year?: string;
  end_year?: string;
};

/** One language, stored as the fact catalog reads it
 *  (backend/app/services/autofill_catalog.py `_languages`). */
export type LanguageEntry = {
  language?: string;
  read?: string;
  speak?: string;
  write?: string;
  native?: boolean;
  fluent?: boolean;
};

export const EDUCATION_FIELDS: { key: keyof EducationEntry; label: string }[] = [
  { key: "school", label: "School" },
  { key: "degree", label: "Degree" },
  { key: "discipline", label: "Major" },
  { key: "gpa", label: "GPA" },
  { key: "start_year", label: "Start year" },
  { key: "end_year", label: "Graduation year" },
];

/** The levels in the words application forms offer, stored as those words. */
export const LANGUAGE_LEVELS = ["Basic", "Intermediate", "Fluent"].map((level) => ({
  value: level,
  label: level,
}));
/** A language select's way back to no answer: the key is removed, never stored as "". */
export const NOT_SET = { value: "not_set", label: "Not set" };

/** Native and fluent are separate answers: forms ask them apart. */
export const LANGUAGE_FIELDS: FieldDef[] = [
  { key: "language", label: "Language" },
  { key: "read", label: "Reading", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "speak", label: "Speaking", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "write", label: "Writing", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] },
  { key: "native", label: "Native speaker", type: "select", boolean: true, options: [NOT_SET, ...YES_NO] },
  { key: "fluent", label: "Fluent", type: "select", boolean: true, options: [NOT_SET, ...YES_NO] },
];

// ------------------------------------------------------------------------------------ The profile

// `only_for` (a company or a city, per `only_for_kind`): set when the question named it, so the answer is
// offered only for a job there.
export type CustomQA = {
  question: string;
  answer: string;
  only_for?: string;
  only_for_kind?: "company" | "city";
};

export type Profile = {
  custom?: CustomQA[];
  education?: EducationEntry[] | EducationEntry;
  languages?: LanguageEntry[];
  [group: string]: unknown;
};

/** The key the per-country work-permit answers live under (backend autofill_profile `BY_COUNTRY`). */
export const BY_COUNTRY = "work_auth_by_country";

export function isBlank(value: unknown): boolean {
  return typeof value !== "string" || !value.trim();
}

export function groupValues(profile: Profile, group: string): Record<string, unknown> {
  const value = profile[group];
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function educationList(profile: Profile): EducationEntry[] {
  const value = profile.education;
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return [value]; // legacy single entry
  return [];
}

/** The "group.key" answers the backend dropped because their question changed (`stale_answers`). */
export function staleAnswers(profile: Profile): string[] {
  const listed = profile.stale_answers;
  return Array.isArray(listed) ? listed.filter((item): item is string => typeof item === "string") : [];
}

/** A yes/no answer from whatever is actually in the profile.
 *
 * THREE WRITERS reach these keys and they do not agree on a type, which is why
 * this is a coercion rather than a read: this form writes booleans, the profile
 * JSON is documented as hand-editable, and the extension's PAUSE ROW writes the
 * user's answer AS TYPED ("Yes", "yes", "No") because the fill engine's
 * `yesNo` passes a string straight through and its option matcher lower-cases
 * before comparing.
 *
 * So the trimming and lower-casing here are load-bearing for a field that
 * declares `boolean: true`, and NOT declaring it is what made this a defect:
 * `fieldValue` then returns the raw string, "Yes" matches no `YES_NO` option
 * value, and the select renders EMPTY. The user opens Profile and the answer
 * they gave in the panel is simply not there, while the engine, which reads
 * the same profile, fills the field correctly. A value stored must render in
 * every reader, and this form is the reader the extension cannot test.
 */
export function booleanAnswer(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  if (value.trim().toLowerCase() === "yes") return true;
  if (value.trim().toLowerCase() === "no") return false;
  return undefined;
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

/** One country's answers with the legacy pair read as typed answers (SYSTEM.md §13 `autofill-work-auth-shape`:
 *  this editor's legacy-on-edit bridge). */
function typedEntry(raw: Record<string, unknown>): Record<string, unknown> {
  const {
    authorized_to_work: legacyAuthorized,
    requires_sponsorship: legacySponsorship,
    ...workAuth
  } = raw;
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
  return workAuth;
}

/** The profile as the editors hold it: every country's work-permit answers typed, and without the one-set
 *  `work_auth` view a read serves beside them (the per-country map is what Profile edits). */
export function profileForEditing(profile: Profile): Profile {
  const { work_auth: _oneSet, work_auth_market: _itsMarket, ...rest } = profile;
  void _oneSet;
  void _itsMarket;
  const stored = groupValues(profile, BY_COUNTRY);
  const byCountry = Object.fromEntries(
    Object.entries(stored).flatMap(([market, entry]) =>
      entry && typeof entry === "object" && !Array.isArray(entry)
        ? [[market, typedEntry(entry as Record<string, unknown>)]]
        : [],
    ),
  );
  return Object.keys(byCountry).length ? { ...rest, [BY_COUNTRY]: byCountry } : rest;
}

/** What a save sends: the profile without the one-set `work_auth` view or the `work_auth_market` a read names
 *  it with, so the server keeps the per-country map it is given (backend autofill_profile `_as_stored`: a
 *  client that knows every country leaves the one set out). */
export function forSaving(profile: Profile): Profile {
  const { work_auth: _oneSet, work_auth_market: _itsMarket, ...rest } = profile;
  void _oneSet;
  void _itsMarket;
  return rest;
}

/** One country's answers, by market key ("UK", never the ISO "GB"). */
export function permitEntry(profile: Profile, market: string): Record<string, unknown> {
  return groupValues(groupValues(profile, BY_COUNTRY), market);
}

/** The profile with one work-permit answer set (undefined removes it) on one country's entry. */
export function withPermit(
  profile: Profile,
  market: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  const byCountry = groupValues(profile, BY_COUNTRY);
  const entry = { ...groupValues(byCountry, market) };
  if (value === undefined || value === "") delete entry[key];
  else entry[key] = value;
  return { ...profile, [BY_COUNTRY]: { ...byCountry, [market]: entry } };
}

export function fieldValue(field: FieldDef, value: unknown): string {
  if (field.boolean) {
    const answer = booleanAnswer(value);
    return answer === undefined ? "" : answer ? "yes" : "no";
  }
  return typeof value === "string" ? value : "";
}

export function storedFieldValue(
  field: FieldDef,
  value: string | null,
): string | boolean | undefined {
  if (!field.boolean) return value ?? "";
  if (value === "yes") return true;
  if (value === "no") return false;
  return undefined;
}

/** Whether a field holds an answer the readers count: a boolean field a Yes or No, a select one of its
 *  options, a text field any words. */
export function answered(field: FieldDef, value: unknown): boolean {
  if (field.boolean) return booleanAnswer(value) !== undefined;
  if (field.type === "select") return Boolean(field.options?.some((option) => option.value === value));
  return !isBlank(value);
}

export type Count = { answered: number; answerable: number };

/** How many of a group's required answers are given: the fields setup readiness counts. */
export function groupCount(profile: Profile, group: string): Count {
  const values = groupValues(profile, group);
  const required = groupFields(group).filter((field) => !field.optional);
  return {
    answered: required.filter((field) => answered(field, values[field.key])).length,
    answerable: required.length,
  };
}

/** How many of one country's required work-permit answers are given, in its vocabulary. */
export function permitCount(profile: Profile, market: string, vocab: string | null | undefined): Count {
  const entry = permitEntry(profile, market);
  const required = permitQuestions(vocab);
  return {
    answered: required.filter((field) => answered(field, entry[field.key])).length,
    answerable: required.length,
  };
}

/** The profile with one answer set in a group (undefined removes it). A field shown only for one answer
 *  goes with that answer: a self-description must not stay stored under "Female", unseen. */
export function withField(
  profile: Profile,
  group: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  const values = { ...groupValues(profile, group) };
  if (value === undefined) {
    delete values[key];
  } else {
    values[key] = value;
  }
  for (const field of groupFields(group)) {
    if (field.when?.[0] === key && field.when[1] !== value) delete values[field.key];
  }
  return { ...profile, [group]: values };
}

/** What "Decline the rest" leaves to you, said beside it in Profile and Setup: `declinedEeo` declines selects
 *  only, and race or ethnicity is typed. */
export const RACE_STAYS_YOURS = "Race or ethnicity has no decline choice, so it stays yours to answer.";

/** "Decline the rest": each diversity select still blank gets its decline option (every one offers the
 *  value "decline", whatever its words), and nothing already answered changes. Empty when nothing is blank. */
export function declinedEeo(profile: Profile): Record<string, string> {
  const eeo = groupValues(profile, "eeo");
  return Object.fromEntries(
    groupFields("eeo").flatMap((field) => {
      if (field.type !== "select" || !isBlank(eeo[field.key])) return [];
      const decline = field.options?.find((option) => option.value === "decline");
      return decline ? [[field.key, decline.value]] : [];
    }),
  );
}

export function withAnswer(
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
export function languageValue(field: FieldDef, stored: unknown): string {
  const value = fieldValue(field, stored);
  if (field.type !== "select") return value;
  return field.options?.find((o) => o.value.toLowerCase() === value.toLowerCase())?.value || NOT_SET.value;
}

// ------------------------------------------------------------------------------------- Next up

/** A required answer still missing: one country's work-permit question, a contact or start-and-pay field,
 *  or the diversity questions as a whole (answered in their fold, beside their consent). */
export type MissingAnswer =
  | { kind: "permit"; market: string; field: FieldDef }
  | { kind: "field"; group: "personal" | "preferences"; field: FieldDef }
  | { kind: "diversity" };

/** One market as Next up reads it (a `MarketOption` from `GET /api/settings/market`). */
type AskedIn = { key: string; work_auth_vocab?: string | null; offers_eeo: boolean };

export function missingKey(item: MissingAnswer): string {
  if (item.kind === "permit") return `permit:${item.market}:${item.field.key}`;
  if (item.kind === "field") return `${item.group}:${item.field.key}`;
  return "diversity";
}

/**
 * Every required answer still missing, in the order Next up asks: each country's work permit first, in the
 * order you apply in (the knockout answers, never guessed), then contact, then start and pay, then the
 * diversity questions where a country you apply in has a checked set. The fields are the ones setup
 * readiness counts, so an empty list is a full ring.
 */
export function missingAnswers(profile: Profile, applyIn: readonly string[], markets: readonly AskedIn[]): MissingAnswer[] {
  const byKey = new Map(markets.map((m) => [m.key, m]));
  const out: MissingAnswer[] = [];
  for (const market of applyIn) {
    const entry = permitEntry(profile, market);
    for (const field of permitQuestions(byKey.get(market)?.work_auth_vocab)) {
      if (!answered(field, entry[field.key])) out.push({ kind: "permit", market, field });
    }
  }
  for (const group of ["personal", "preferences"] as const) {
    const values = groupValues(profile, group);
    for (const field of groupFields(group)) {
      if (!field.optional && !answered(field, values[field.key])) out.push({ kind: "field", group, field });
    }
  }
  const offered = applyIn.some((market) => byKey.get(market)?.offers_eeo);
  if (offered && groupCount(profile, "eeo").answered < groupCount(profile, "eeo").answerable) {
    out.push({ kind: "diversity" });
  }
  return out;
}
