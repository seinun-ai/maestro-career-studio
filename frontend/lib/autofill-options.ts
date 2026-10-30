/**
 * How a stored answer to a form question reads, counts and saves, shared by Profile (`components/profile/*`)
 * and Setup (`components/setup/*`). The questions come from the backend: `GET /api/settings/autofill/questions`
 * serves the set for where you live and apply (`QuestionSet`, from `services/data/form_questions.yaml`), and
 * every helper that needs a question takes that set. Nothing here mirrors a backend question list. Pure, so
 * `node --test` loads it (lib/autofill-options.test.ts): it imports only types, which the loader erases.
 */
import type { FieldDef, QuestionSet } from "./types";

export type { FieldDef, GroupDef } from "./types";

export const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

/** How many saved answers a fill reads: `MAX_CUSTOM` in backend/app/services/autofill_catalog.py. */
export const CUSTOM_IN_USE = 30;

/** One group's fields, by key ("personal", "eeo", "eligibility", "preferences"), as served: the state line is
 *  already named and counted for where you live. A group the set lacks has none. */
export function groupFields(questions: QuestionSet, key: string): FieldDef[] {
  return questions.groups.find((group) => group.key === key)?.fields ?? [];
}

// ------------------------------------------------------------------ Work permits, per country

/** The countries whose work permit is asked: the served set's own keys, in the order you apply in (the server
 *  builds them that way). Never the market setting's list, which can change before the set is read again. */
export function permitMarkets(questions: QuestionSet): string[] {
  return Object.keys(questions.permits);
}

/** One country's work-permit fields, in its own words: its required questions, then when the permit runs out
 *  (optional). Served per market you apply in ("UK", never "GB"); any other market has none, never another
 *  country's. */
export function permitFields(questions: QuestionSet, market: string): FieldDef[] {
  return questions.permits[market] ?? [];
}

/** One country's required work-permit questions: the ones setup readiness counts. */
export function permitQuestions(questions: QuestionSet, market: string): FieldDef[] {
  return permitFields(questions, market).filter((field) => !field.optional);
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

/** How many of a group's required answers are given: the fields setup readiness counts, as served for where
 *  you live. */
export function groupCount(profile: Profile, questions: QuestionSet, group: string): Count {
  const values = groupValues(profile, group);
  const required = groupFields(questions, group).filter((field) => !field.optional);
  return {
    answered: required.filter((field) => answered(field, values[field.key])).length,
    answerable: required.length,
  };
}

/** How many of one country's required work-permit answers are given, in its own questions. */
export function permitCount(profile: Profile, questions: QuestionSet, market: string): Count {
  const entry = permitEntry(profile, market);
  const required = permitQuestions(questions, market);
  return {
    answered: required.filter((field) => answered(field, entry[field.key])).length,
    answerable: required.length,
  };
}

/** Whether every required work-permit answer of one country is given. A country the set serves no questions
 *  for is open, never answered: a knockout answer is never taken as given. */
export function permitAnswered(profile: Profile, questions: QuestionSet, market: string): boolean {
  const count = permitCount(profile, questions, market);
  return count.answerable > 0 && count.answered === count.answerable;
}

/** The profile with one answer set in a group (undefined removes it). A field shown only for one answer
 *  goes with that answer: a self-description must not stay stored under "Female", unseen. */
export function withField(
  profile: Profile,
  questions: QuestionSet,
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
  for (const field of groupFields(questions, group)) {
    if (field.when?.[0] === key && field.when[1] !== value) delete values[field.key];
  }
  return { ...profile, [group]: values };
}

/** What "Decline the rest" leaves to you, said beside it in Profile and Setup: `declinedEeo` declines selects
 *  only, and race or ethnicity is typed. */
export const RACE_STAYS_YOURS = "Race or ethnicity has no decline choice, so it stays yours to answer.";

/** "Decline the rest": each diversity select still blank gets its decline option (every one offers the
 *  value "decline", whatever its words), and nothing already answered changes. Empty when nothing is blank. */
export function declinedEeo(profile: Profile, questions: QuestionSet): Record<string, string> {
  const eeo = groupValues(profile, "eeo");
  return Object.fromEntries(
    groupFields(questions, "eeo").flatMap((field) => {
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

export function missingKey(item: MissingAnswer): string {
  if (item.kind === "permit") return `permit:${item.market}:${item.field.key}`;
  if (item.kind === "field") return `${item.group}:${item.field.key}`;
  return "diversity";
}

/**
 * Every required answer still missing, in the order Next up asks: each served country's work permit first, in
 * the order you apply in (`permitMarkets`; the knockout answers, never guessed), then contact, then start and
 * pay, then the diversity questions where a country you apply in has a checked set (`offers_eeo`). The fields
 * are the ones setup readiness counts, as served for where you live, so an empty list is a full ring.
 */
export function missingAnswers(profile: Profile, questions: QuestionSet): MissingAnswer[] {
  const out: MissingAnswer[] = [];
  for (const market of permitMarkets(questions)) {
    const entry = permitEntry(profile, market);
    for (const field of permitQuestions(questions, market)) {
      if (!answered(field, entry[field.key])) out.push({ kind: "permit", market, field });
    }
  }
  for (const group of ["personal", "preferences"] as const) {
    const values = groupValues(profile, group);
    for (const field of groupFields(questions, group)) {
      if (!field.optional && !answered(field, values[field.key])) out.push({ kind: "field", group, field });
    }
  }
  const eeo = groupCount(profile, questions, "eeo");
  if (questions.offers_eeo && eeo.answered < eeo.answerable) out.push({ kind: "diversity" });
  return out;
}
