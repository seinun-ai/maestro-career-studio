/**
 * How a stored answer to a form question reads, counts and saves, shared by Profile (`components/profile/*`)
 * and Setup (`components/setup/*`). The questions come from the backend: `GET /api/settings/autofill/questions`
 * serves the set for where you live and apply (`QuestionSet`, from `services/data/form_questions.yaml`), and
 * every helper that needs a question takes that set. Nothing here mirrors a backend question list. Pure, so
 * `node --test` loads it (lib/autofill-options.test.ts): it imports only types, which the loader erases.
 */
import type { Country, CountryQuestions, DerivedAnswer, FieldDef, MarketOption, QuestionSet } from "./types";

export type { CountryQuestions, DerivedAnswer, FieldDef } from "./types";

export const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

/** How many saved answers a fill reads: `MAX_CUSTOM` in backend/app/services/autofill_catalog.py. */
export const CUSTOM_IN_USE = 30;

/** One group's fields, by key ("personal", "eeo", "eligibility", "preferences"), as served: the state line is
 *  already named and counted for where you live. A group the set lacks has none. */
export function groupFields(questionSet: QuestionSet, key: string): FieldDef[] {
  return questionSet.groups.find((group) => group.key === key)?.fields ?? [];
}

/** Contact's questions: the personal group's as served, less citizenship (`type: "countries"`, a list of
 *  countries, never a line of text), which Country answers asks and setup readiness counts beside the work
 *  permits it settles. */
export function contactFields(questionSet: QuestionSet): FieldDef[] {
  return groupFields(questionSet, "personal").filter((field) => field.type !== "countries");
}

/** The citizenship question ("Citizen of", a list of countries), as served in the personal group. */
export function citizenshipField(questionSet: QuestionSet): FieldDef | undefined {
  return groupFields(questionSet, "personal").find((field) => field.type === "countries");
}

/** Whether a field is asked beside the other answers of its list: `when` shows it only for one answer of
 *  another field, `unless` hides it for some (an expiry, for a status that never runs out). */
export function fieldShown(field: FieldDef, values: Record<string, unknown>): boolean {
  if (field.when && values[field.when[0]] !== field.when[1]) return false;
  const shownUnless = field.unless;
  if (shownUnless && shownUnless[1].some((value) => value === values[shownUnless[0]])) return false;
  return true;
}

/** `values` with `key` set (undefined or "" removes it), and every field of `fields` that answer hides removed
 *  with it: a self-description must not stay stored under "Female", nor an expiry under "Citizen", unseen. */
function withAnswerIn(
  values: Record<string, unknown>,
  fields: readonly FieldDef[],
  key: string,
  value: string | boolean | undefined,
  { keepBlank = false } = {},
): Record<string, unknown> {
  const next = { ...values };
  if (value === undefined || (value === "" && !keepBlank)) delete next[key];
  else next[key] = value;
  for (const field of fields) {
    const dependsOn = field.when?.[0] === key || field.unless?.[0] === key;
    if (dependsOn && !fieldShown(field, next)) delete next[field.key];
  }
  return next;
}

// ------------------------------------------------------------------ Country answers, per country

/** One country's served questions, by market key ("UK", never "GB"); none for a country the set lacks. */
export function countryQuestions(questionSet: QuestionSet, market: string): CountryQuestions | undefined {
  return questionSet.countries.find((country) => country.market === market);
}

/** The countries whose questions are asked: the served set's own, in the order you apply in (the server builds
 *  them that way). Never the market setting's list, which can change before the set is read again. */
export function permitMarkets(questionSet: QuestionSet): string[] {
  return questionSet.countries.map((country) => country.market);
}

/** One country's work-permit fields, in its own words: its required questions, then when the permit runs out
 *  (optional). Served per market you apply in ("UK", never "GB"); any other market has none, never another
 *  country's. */
export function permitFields(questionSet: QuestionSet, market: string): FieldDef[] {
  return countryQuestions(questionSet, market)?.permits ?? [];
}

/** One country's required work-permit questions: the ones setup readiness counts. */
export function permitQuestions(questionSet: QuestionSet, market: string): FieldDef[] {
  return permitFields(questionSet, market).filter((field) => !field.optional);
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
  /** The CEFR level (A1 to C2), asked while a country you apply in asks it (`QuestionSet.language_fields`). */
  cefr?: string;
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

/** Each language's fields: these, then the ones a country you apply in asks besides (the CEFR level), whose
 *  selects offer "Not set" too, so an answer can be taken back. */
export function languageFields(questionSet: QuestionSet): FieldDef[] {
  const served = (questionSet.language_fields ?? []).map((field) =>
    field.type === "select" ? { ...field, options: [NOT_SET, ...(field.options ?? [])] } : field,
  );
  return [...LANGUAGE_FIELDS, ...served];
}

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
/** The key each country's own answers live under, keyed by market the same way (`ANSWERS_BY_COUNTRY`). */
export const ANSWERS_BY_COUNTRY = "answers_by_country";

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

/** One country's work-permit answers, by market key ("UK", never the ISO "GB"). */
export function permitEntry(profile: Profile, market: string): Record<string, unknown> {
  return groupValues(groupValues(profile, BY_COUNTRY), market);
}

/** The profile with one work-permit answer set (undefined removes it) on one country's entry. An answer that
 *  hides another of that country's fields removes it: a citizen's expiry is never kept. */
export function withPermit(
  profile: Profile,
  questionSet: QuestionSet,
  market: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  const byCountry = groupValues(profile, BY_COUNTRY);
  const entry = withAnswerIn(groupValues(byCountry, market), permitFields(questionSet, market), key, value);
  return { ...profile, [BY_COUNTRY]: { ...byCountry, [market]: entry } };
}

/** The country answer that is a country's pay, and the key the pay of the country you live in is kept under
 *  instead (`preferences.desired_salary`: backend autofill_profile `_with_home_pay` folds a home entry's pay
 *  into it on every save and read). */
export const EXPECTED_PAY = "expected_pay";
const HOME_PAY = "desired_salary";

/** A country as its own answers are read and written: its market key, and whether it is where you live. */
export type CountryKey = Pick<CountryQuestions, "market" | "home">;

/** One country's own answers (`answers_by_country`), by market key. Where you live (`home`), its pay is the
 *  desired salary, the one place the server keeps the home's figure. */
export function countryAnswerEntry(profile: Profile, country: CountryKey): Record<string, unknown> {
  const entry = groupValues(groupValues(profile, ANSWERS_BY_COUNTRY), country.market);
  const pay = country.home ? groupValues(profile, "preferences")[HOME_PAY] : undefined;
  return pay === undefined ? entry : { ...entry, [EXPECTED_PAY]: pay };
}

/** The profile with one of a country's own answers set (undefined or "" removes it); every other country's
 *  answers stay as they are. The home's pay is written as the desired salary, so a save never sends the home's
 *  figure in two places. */
export function withCountryAnswer(
  profile: Profile,
  country: CountryKey,
  key: string,
  value: string | boolean | undefined,
): Profile {
  if (country.home && key === EXPECTED_PAY) {
    return { ...profile, preferences: withAnswerIn(groupValues(profile, "preferences"), [], HOME_PAY, value) };
  }
  const byCountry = groupValues(profile, ANSWERS_BY_COUNTRY);
  const entry = withAnswerIn(groupValues(byCountry, country.market), [], key, value);
  return { ...profile, [ANSWERS_BY_COUNTRY]: { ...byCountry, [country.market]: entry } };
}

/** The citizenships stored, as entries: a list as written, or the parts of a plain string (an older save or a
 *  hand edit: "India, Ireland"), so it still shows. A save from the picker writes codes in its place. */
export function citizenshipEntries(profile: Profile): string[] {
  const value = groupValues(profile, "personal").citizenships;
  const parts = Array.isArray(value) ? value : typeof value === "string" ? value.split(/[,;]/) : [];
  return parts.filter((part): part is string => !isBlank(part)).map((part) => part.trim());
}

/** Each way a country is named, folded, to its ISO code: its name, its aliases ("uk" for GB) and its code, from
 *  the country list (`GET /api/countries`), read as the server's `countries.normalize` reads them. */
export type CountryCodes = ReadonlyMap<string, string>;

/** Folded as the server's `countries._fold`: lower case, without accents, with straight apostrophes. */
function foldCountry(text: string): string {
  return text
    .trim()
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[\u2018\u2019\u02bc]/g, "'");
}

/** The country list as `CountryCodes`. A code wins over a name or alias spelled the same, then an alias over a
 *  name, as the server reads them. */
export function countryCodes(countries: readonly Country[]): CountryCodes {
  const codes = new Map<string, string>();
  for (const country of countries) codes.set(foldCountry(country.name), country.code);
  for (const country of countries) for (const alias of country.aliases ?? []) codes.set(foldCountry(alias), country.code);
  for (const country of countries) codes.set(foldCountry(country.code), country.code);
  return codes;
}

/** The ISO code an entry names (its code in any case, its name, or an alias: "UK" is GB), or null. */
export function countryCode(codes: CountryCodes, entry: string): string | null {
  return codes.get(foldCountry(entry)) ?? null;
}

/**
 * Whether citizenship is stored other than as the picker stores it, as codes: a plain string (an older save, a
 * hand edit), or, once the country list is read (`codes`), a list naming a country by name or alias ("India",
 * "UK") or by a code in another case. It shows in the picker, and `withCitizenshipList` stores it as codes.
 */
export function citizenshipIsLoose(profile: Profile, codes: CountryCodes | null): boolean {
  const stored = groupValues(profile, "personal").citizenships;
  if (typeof stored === "string") return true;
  if (!codes || !Array.isArray(stored)) return false;
  return citizenshipEntries(profile).some((entry) => countryCode(codes, entry) !== entry);
}

/**
 * The profile with a loose citizenship (`citizenshipIsLoose`) stored as codes, each once: each entry by its code,
 * name or alias, and an entry that names no country dropped, as the server's save does ("Narnia"). Before the
 * country list is read (`codes` null) a plain string is stored as the list of its parts, which the server turns
 * into codes. Unchanged when it is stored as codes already, or absent.
 */
export function withCitizenshipList(profile: Profile, codes: CountryCodes | null): Profile {
  if (!citizenshipIsLoose(profile, codes)) return profile;
  const entries = citizenshipEntries(profile);
  return withCitizenships(
    profile,
    codes ? entries.flatMap((entry) => countryCode(codes, entry) ?? []) : entries,
  );
}

/** The profile with these citizenships (ISO codes, each once; none removes the answer). The server stores
 *  codes, and what a citizenship settles is read again with the questions. */
export function withCitizenships(profile: Profile, codes: readonly string[]): Profile {
  const personal = { ...groupValues(profile, "personal") };
  const unique = [...new Set(codes.filter((code) => !isBlank(code)))];
  if (unique.length) personal.citizenships = unique;
  else delete personal.citizenships;
  return { ...profile, personal };
}

/** The served `settled` answers whose citizenship is still among yours: removing one stops what it settled at
 *  once, before the questions are read again. A citizenship held by name (a hand edit, or a save from before
 *  codes) settles nothing here, though the server reads names (`countries.codes_in`) and settles from them: this
 *  side treats a name list as not yet answered, so Next up asks it and the next save stores codes
 *  (`withCitizenshipList`), and the two agree from then on. */
function stillCitizen(profile: Profile, settled: Record<string, DerivedAnswer>): Record<string, DerivedAnswer> {
  const codes = new Set(citizenshipEntries(profile).map((entry) => entry.toUpperCase()));
  return Object.fromEntries(Object.entries(settled).filter(([, answer]) => codes.has(answer.via.toUpperCase())));
}

/** Whether an answer you gave in `market` differs from one of `settled`: you know something the rule does not,
 *  so it settles nothing there. A blank or unusable answer differs from nothing. */
export function differsFromSettled(
  profile: Profile,
  questionSet: QuestionSet,
  market: string,
  settled: Record<string, DerivedAnswer>,
): boolean {
  const entry = permitEntry(profile, market);
  const fields = permitFields(questionSet, market);
  return Object.entries(stillCitizen(profile, settled)).some(([key, answer]) => {
    const field = fields.find((f) => f.key === key);
    if (!field || !answered(field, entry[key])) return false;
    return (field.boolean ? booleanAnswer(entry[key]) : entry[key]) !== answer.value;
  });
}

/**
 * The work-permit answers a citizenship settles in one country, as far as the answers on screen allow. The
 * server decides them (`derived`, from backend `autofill_derive.derived_in_effect` over what it last read);
 * this only narrows that until the questions are read again: none once an answer you gave there differs from
 * one it settles, and none from a citizenship you removed. It never settles anything the server did not.
 */
export function derivedPermits(profile: Profile, questionSet: QuestionSet, market: string): Record<string, DerivedAnswer> {
  const settled = stillCitizen(profile, countryQuestions(questionSet, market)?.derived ?? {});
  return differsFromSettled(profile, questionSet, market, settled) ? {} : settled;
}

/** One country's required permit questions still open: neither answered by you nor settled by your
 *  citizenship. What Next up and Setup ask, and what the count leaves out. */
export function openPermitFields(profile: Profile, questionSet: QuestionSet, market: string): FieldDef[] {
  const entry = permitEntry(profile, market);
  const derived = derivedPermits(profile, questionSet, market);
  return permitQuestions(questionSet, market).filter(
    (field) => !(field.key in derived) && !answered(field, entry[field.key]),
  );
}

/** The key of when a country's permit runs out: optional, and never asked of a right to work a citizenship
 *  gives (that one does not run out). */
export const PERMIT_EXPIRY = "authorization_expires_on";

/**
 * One country's permit fields as Country answers shows them: by the answers as the fill reads them (a status
 * your citizenship settles hides its expiry, as one you gave does), and without the expiry while your
 * citizenship settles that country, unless you are answering one of its questions yourself (`answering`) or an
 * expiry is stored, which always shows.
 */
export function shownPermitFields(
  profile: Profile,
  questionSet: QuestionSet,
  market: string,
  answering: readonly string[] = [],
): FieldDef[] {
  const answers = permitAnswers(profile, questionSet, market);
  const citizen = Object.keys(derivedPermits(profile, questionSet, market)).length > 0 && answering.length === 0;
  const stored = permitEntry(profile, market);
  return permitFields(questionSet, market).filter(
    (field) =>
      fieldShown(field, answers) && !(citizen && field.key === PERMIT_EXPIRY && isBlank(stored[field.key])),
  );
}

/** One country's permit answers as the fill reads them: each one you gave, over the ones a citizenship
 *  settles. What decides which of its fields are shown (`fieldShown`), and what its tile says. */
export function permitAnswers(profile: Profile, questionSet: QuestionSet, market: string): Record<string, unknown> {
  const entry = permitEntry(profile, market);
  const settled = Object.entries(derivedPermits(profile, questionSet, market)).map(([key, d]) => [key, d.value]);
  const given = permitFields(questionSet, market).filter((field) => answered(field, entry[field.key]));
  return {
    ...Object.fromEntries(settled),
    ...Object.fromEntries(given.map((field) => [field.key, field.boolean ? booleanAnswer(entry[field.key]) : entry[field.key]])),
  };
}

export function fieldValue(field: FieldDef, value: unknown): string {
  if (field.boolean) {
    const answer = booleanAnswer(value);
    return answer === undefined ? "" : answer ? "yes" : "no";
  }
  if (field.type === "number" && typeof value === "number" && Number.isFinite(value)) return String(value);
  return typeof value === "string" ? value : "";
}

/** A stored answer in words, as its field offers it ("Yes", "Citizen"); a typed answer as written. */
export function answerWords(field: FieldDef, value: unknown): string {
  const shown = fieldValue(field, value);
  return field.options?.find((option) => option.value === shown)?.label ?? shown;
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
 *  options, a list of countries at least one (the save stores each as its code), a number any number, a text
 *  field any words. */
export function answered(field: FieldDef, value: unknown): boolean {
  if (field.boolean) return booleanAnswer(value) !== undefined;
  if (field.type === "select") return Boolean(field.options?.some((option) => option.value === value));
  if (field.type === "countries") return Array.isArray(value) && value.some((entry) => !isBlank(entry));
  if (field.type === "number" && typeof value === "number") return Number.isFinite(value);
  return !isBlank(value);
}

/** Whether a list's stored `values` answer a field: its own value does (`answered`), or, until that is given,
 *  the text under its older key (`legacy`: notice in words, from before it was days), as setup readiness reads
 *  it (backend setup_status `_given`). So an older answer is never counted set and listed missing at once, nor
 *  asked again by Next up. */
export function answeredIn(field: FieldDef, values: Record<string, unknown>): boolean {
  return answered(field, values[field.key]) || (field.legacy !== undefined && !isBlank(values[field.legacy]));
}

export type Count = { answered: number; answerable: number };

/** How many of a group's required answers are given: the fields setup readiness counts there, as served for
 *  where you live. Citizenship is not one of personal's: it counts beside the work permits it settles. */
export function groupCount(profile: Profile, questionSet: QuestionSet, group: string): Count {
  const fields = group === "personal" ? contactFields(questionSet) : groupFields(questionSet, group);
  return countOf(groupValues(profile, group), fields);
}

function countOf(values: Record<string, unknown>, fields: readonly FieldDef[]): Count {
  const required = fields.filter((field) => !field.optional);
  return {
    answered: required.filter((field) => answeredIn(field, values)).length,
    answerable: required.length,
  };
}

/** How many of one country's required work-permit answers are given, in its own questions: each you gave, and
 *  each your citizenship settles there (`derivedPermits`), as setup readiness counts them. */
export function permitCount(profile: Profile, questionSet: QuestionSet, market: string): Count {
  const answerable = permitQuestions(questionSet, market).length;
  return { answered: answerable - openPermitFields(profile, questionSet, market).length, answerable };
}

/** Whether citizenship is answered: at least one country, as the picker saves it (codes). Once the country list
 *  is read (`codes`), a list naming a country by name or alias (a hand edit) is not, since it settles nothing
 *  here until it is stored as codes (`citizenshipIsLoose`). A set that does not ask it has nothing to answer. */
export function citizenshipAnswered(profile: Profile, questionSet: QuestionSet, codes: CountryCodes | null = null): boolean {
  const field = citizenshipField(questionSet);
  return !field || (answered(field, groupValues(profile, "personal")[field.key]) && !citizenshipIsLoose(profile, codes));
}

/** Whether every required work-permit answer of one country is given or settled. A country the set serves no
 *  questions for is open, never answered: a knockout answer is never taken as given. */
export function permitAnswered(profile: Profile, questionSet: QuestionSet, market: string): boolean {
  const count = permitCount(profile, questionSet, market);
  return count.answerable > 0 && count.answered === count.answerable;
}

/** One country's required answers of its own still not given: its pay where you live (the served set requires
 *  it there, `home`), and none elsewhere, where they are optional. A country the set lacks has none. */
export function countryAnswersOpen(profile: Profile, questionSet: QuestionSet, market: string): FieldDef[] {
  const country = countryQuestions(questionSet, market);
  if (!country) return [];
  const entry = countryAnswerEntry(profile, country);
  return country.answers.filter((field) => !field.optional && !answeredIn(field, entry));
}

/** Whether one country's set is done in Country answers: its work permits (`permitAnswered`) and its own
 *  required answers. Setup status counts the home's pay on its own (`home_pay`, beside the groups), and
 *  Profile's ring holds Country answers open on it; Setup's permit step reads the permits alone, since Setup
 *  never asks pay (Decision 8 of docs/plans/2026-11-02-start-and-pay.md). */
export function countryDone(profile: Profile, questionSet: QuestionSet, market: string): boolean {
  return permitAnswered(profile, questionSet, market) && countryAnswersOpen(profile, questionSet, market).length === 0;
}

/** Open answers of a country's own in words: its pay by name, else how many. */
export function openAnswersWords(open: readonly FieldDef[]): string {
  if (open.length === 1 && open[0].key === EXPECTED_PAY) return "expected pay not given";
  return `${open.length} ${open.length === 1 ? "answer" : "answers"} not given`;
}

/** How many of one country's set of required questions are answered: its work permits, then its own required
 *  answers. What its line in Country answers and Next up count while they show that country. */
export function countrySetCount(profile: Profile, questionSet: QuestionSet, market: string): Count {
  const permits = permitCount(profile, questionSet, market);
  const country = countryQuestions(questionSet, market);
  const own = country ? countOf(countryAnswerEntry(profile, country), country.answers) : { answered: 0, answerable: 0 };
  return { answered: permits.answered + own.answered, answerable: permits.answerable + own.answerable };
}

/** The profile with one answer set in a group (undefined removes it). A field shown only for one answer
 *  goes with that answer (`when`, `unless`): a self-description must not stay stored under "Female", unseen. */
export function withField(
  profile: Profile,
  questionSet: QuestionSet,
  group: string,
  key: string,
  value: string | boolean | undefined,
): Profile {
  const values = withAnswerIn(groupValues(profile, group), groupFields(questionSet, group), key, value, {
    keepBlank: true,
  });
  return { ...profile, [group]: values };
}

/** The countries the diversity questions are asked for, named as served: each country the served set lists
 *  (`countries`, the ones you chose, in the order you apply in) whose market has a checked set (`offers_eeo`,
 *  from the market list; never decided here). None while the set offers none, so with no country chosen it
 *  names none, though the market setting still stores its default. */
export function diversityCountries(questionSet: QuestionSet, markets: readonly MarketOption[]): string[] {
  if (!questionSet.offers_eeo) return [];
  return questionSet.countries.flatMap((country) =>
    markets.find((m) => m.key === country.market)?.offers_eeo ? [country.label] : [],
  );
}

/** What "Decline the rest" leaves to you, said beside it in Profile and Setup: `declinedEeo` declines selects
 *  only, and race or ethnicity is typed. */
export const RACE_STAYS_YOURS = "Race or ethnicity has no decline choice, so it stays yours to answer.";

/** "Decline the rest": each diversity select still blank gets its decline option (every one offers the
 *  value "decline", whatever its words), and nothing already answered changes. Empty when nothing is blank. */
export function declinedEeo(profile: Profile, questionSet: QuestionSet): Record<string, string> {
  const eeo = groupValues(profile, "eeo");
  return Object.fromEntries(
    groupFields(questionSet, "eeo").flatMap((field) => {
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

/** A required answer still missing: where you apply while no country is chosen (answered in the Where you
 *  apply tile), citizenship (asked with its country picker), one country's work-permit question or required
 *  answer of its own (the home's pay), a contact or start-and-pay field, or the diversity questions as a whole
 *  (answered in their fold, beside their consent). */
export type MissingAnswer =
  | { kind: "where" }
  | { kind: "citizenship"; field: FieldDef }
  | { kind: "permit"; market: string; field: FieldDef }
  | { kind: "own"; market: string; field: FieldDef }
  | { kind: "field"; group: "personal" | "preferences"; field: FieldDef }
  | { kind: "diversity" };

export function missingKey(item: MissingAnswer): string {
  if (item.kind === "where" || item.kind === "citizenship") return item.kind;
  if (item.kind === "permit" || item.kind === "own") return `${item.kind}:${item.market}:${item.field.key}`;
  if (item.kind === "field") return `${item.group}:${item.field.key}`;
  return "diversity";
}

/** A missing answer Next up asks in a control of its own, in the list that stores it. */
export type AnswerInPlace = Extract<MissingAnswer, { kind: "permit" | "own" | "field" }>;

/** A country by its market key, as its own answers are read: the served one, else the key alone. */
function countryRef(questionSet: QuestionSet, market: string): CountryKey {
  return countryQuestions(questionSet, market) ?? { market };
}

/** What a missing answer holds now: a permit in its country's entry, a country's own answer as
 *  `countryAnswerEntry` reads it (the home's pay is the desired salary), any other in its group. */
export function missingValue(profile: Profile, questionSet: QuestionSet, item: AnswerInPlace): unknown {
  const key = item.field.key;
  if (item.kind === "permit") return permitEntry(profile, item.market)[key];
  if (item.kind === "own") return countryAnswerEntry(profile, countryRef(questionSet, item.market))[key];
  return groupValues(profile, item.group)[key];
}

/** The profile with a missing answer set (undefined removes it) where its list stores it, through that list's
 *  own writer (`withPermit`, `withCountryAnswer`, `withField`). */
export function withMissingAnswer(
  profile: Profile,
  questionSet: QuestionSet,
  item: AnswerInPlace,
  value: string | boolean | undefined,
): Profile {
  const key = item.field.key;
  if (item.kind === "permit") return withPermit(profile, questionSet, item.market, key, value);
  if (item.kind === "own") return withCountryAnswer(profile, countryRef(questionSet, item.market), key, value);
  return withField(profile, questionSet, item.group, key, value);
}

/**
 * Every required answer still missing, in the order Next up asks: where you apply while no country is chosen
 * (`questionSet.chosen`), first as in Setup, since the countries decide every country's question that follows
 * (unchosen, none is asked, so every form pauses on them); then citizenship, since it settles some work permits
 * (Country answers asks it, with a country picker, never Contact), then each served country's work permits, in
 * the order you apply in (`permitMarkets`; the knockout answers, never guessed, and none your citizenship
 * settles), each followed by that country's required answers of its own (the home's pay), then contact, then
 * start and pay, then the diversity questions where a country you apply in has a checked set (`offers_eeo`).
 * The fields are the ones setup readiness counts, as served for where you live, and an answer under a field's
 * older key counts (`answeredIn`). A citizenship held by name is missing once the country list is read
 * (`codes`): Next stores it as codes.
 */
export function missingAnswers(
  profile: Profile,
  questionSet: QuestionSet,
  codes: CountryCodes | null = null,
): MissingAnswer[] {
  const out: MissingAnswer[] = questionSet.chosen ? [] : [{ kind: "where" }];
  const citizenship = citizenshipField(questionSet);
  if (citizenship && !citizenship.optional && !citizenshipAnswered(profile, questionSet, codes)) {
    out.push({ kind: "citizenship", field: citizenship });
  }
  for (const market of permitMarkets(questionSet)) {
    for (const field of openPermitFields(profile, questionSet, market)) out.push({ kind: "permit", market, field });
    for (const field of countryAnswersOpen(profile, questionSet, market)) out.push({ kind: "own", market, field });
  }
  for (const group of ["personal", "preferences"] as const) {
    const values = groupValues(profile, group);
    for (const field of group === "personal" ? contactFields(questionSet) : groupFields(questionSet, group)) {
      if (!field.optional && !answeredIn(field, values)) out.push({ kind: "field", group, field });
    }
  }
  const eeo = groupCount(profile, questionSet, "eeo");
  if (questionSet.offers_eeo && eeo.answered < eeo.answerable) out.push({ kind: "diversity" });
  return out;
}
