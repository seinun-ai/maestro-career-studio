import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answered,
  answeredIn,
  citizenshipAnswered,
  citizenshipEntries,
  citizenshipIsLoose,
  contactFields,
  countryAnswerEntry,
  countryAnswered,
  countryAnswersOpen,
  countryCode,
  countryCodes,
  countryCount,
  declinedEeo,
  derivedPermits,
  differsFromSettled,
  diversityCountries,
  fieldShown,
  forSaving,
  groupCount,
  groupFields,
  languageFields,
  missingAnswers,
  missingKey,
  missingValue,
  openPermitFields,
  permitAnswers,
  permitCount,
  permitAnswered,
  permitEntry,
  permitFields,
  permitMarkets,
  permitQuestions,
  profileForEditing,
  shownPermitFields,
  withCitizenshipList,
  withCitizenships,
  withCountryAnswer,
  withField,
  withMissingAnswer,
  withPermit,
} from "./autofill-options.ts";
import type { DerivedAnswer, FieldDef, MarketOption, QuestionSet } from "./types.ts";

// A small set in the served shape (GET /api/settings/autofill/questions; the backend resolves it and its tests
// pin the words). A node-tested lib file cannot import another lib file's values, so it is built here.
const YES_NO = [{ value: "yes", label: "Yes" }, { value: "no", label: "No" }];
const yesNo = (key: string, label: string): FieldDef => ({ key, label, type: "select", boolean: true, options: YES_NO });
const select = (key: string, label: string, values: string[]): FieldDef => ({
  key,
  label,
  type: "select",
  options: values.map((value) => ({ value, label: value })),
});
const EXPIRES: FieldDef = { key: "authorization_expires_on", label: "Authorization expires on", type: "date", optional: true };
// The US expiry is not asked of a status that never runs out (the server sets `unless` from its status list).
const US_EXPIRES: FieldDef = { ...EXPIRES, unless: ["status", ["citizen", "permanent_resident"]] };
const PERMITS: Record<string, FieldDef[]> = {
  US: [
    select("status", "Work authorization status", ["citizen", "permanent_resident", "h1b"]),
    yesNo("authorized_now", "Authorized to work in the U.S. now?"),
    yesNo("sponsorship_now", "Do you need visa sponsorship now?"),
    yesNo("sponsorship_future", "Will you need visa sponsorship later?"),
    US_EXPIRES,
  ],
  UK: [
    yesNo("authorized_now", "Do you have the right to work in the UK now?"),
    yesNo("sponsorship_now", "Do you need visa sponsorship to work in the UK now?"),
    yesNo("sponsorship_future", "Will you need visa sponsorship in the UK later?"),
    EXPIRES,
  ],
  DE: [
    yesNo("authorized_now", "Can you work in this country now?"),
    yesNo("sponsorship_now", "Do you need visa sponsorship now?"),
    yesNo("sponsorship_future", "Will you need visa sponsorship later?"),
    EXPIRES,
  ],
};
const LABELS: Record<string, string> = { US: "United States", UK: "United Kingdom", DE: "Germany" };
const ANSWERS: FieldDef[] = [{ key: "expected_pay", label: "Expected salary", optional: true }];
const STATE: FieldDef = { key: "state", label: "State", byHome: "state" };
type Settled = Record<string, Record<string, DerivedAnswer>>;

/** The set for `applyIn`, with the state line as the server resolved it for where you live, and the permit
 *  answers a citizenship settles per country (`derived`). */
function servedFor(
  applyIn: string[],
  { state = STATE, offersEeo = true, derived = {} as Settled } = {},
): QuestionSet {
  return {
    groups: [
      {
        key: "personal",
        title: "Personal details",
        fields: [
          { key: "first_name", label: "First name" },
          { key: "last_name", label: "Last name" },
          { key: "email", label: "Email" },
          { key: "address_2", label: "Address line 2", optional: true },
          state,
          { key: "linkedin", label: "LinkedIn profile link", optional: true },
          { key: "github", label: "GitHub link", optional: true },
          { key: "website", label: "Website", optional: true },
        ],
      },
      {
        key: "eeo",
        title: "Diversity questions (voluntary)",
        fields: [
          select("veteran_status", "Are you a veteran?", ["no", "yes", "decline"]),
          select("disability_status", "Disability status", ["no", "yes", "decline"]),
          select("gender", "Gender", ["male", "female", "self_describe", "decline"]),
          { key: "gender_self_describe", label: "How you describe your gender", optional: true, when: ["gender", "self_describe"] },
          select("hispanic_latino", "Hispanic or Latino?", ["yes", "no", "decline"]),
          { key: "race_ethnicity", label: "Race or ethnicity", optional: true },
        ],
      },
      { key: "eligibility", title: "Eligibility", fields: [{ ...yesNo("over_18", "Are you 18 or older?"), optional: true }] },
      {
        key: "preferences",
        title: "Preferences",
        fields: [{ key: "desired_salary", label: "Desired salary" }, yesNo("willing_to_relocate", "Willing to relocate?")],
      },
    ],
    countries: applyIn.map((market) => ({
      market,
      label: LABELS[market],
      permits: PERMITS[market],
      answers: ANSWERS,
      ...(derived[market] ? { derived: derived[market] } : {}),
    })),
    offers_eeo: offersEeo,
    chosen: true,
  };
}

const ALL = servedFor(["US", "UK", "DE"]);
const keys = (market: string) => permitQuestions(ALL, market).map((f) => f.key);

test("each country's required questions are its own served ones: the visa status only where it is served", () => {
  assert.deepEqual(keys("US"), ["status", "authorized_now", "sponsorship_now", "sponsorship_future"]);
  assert.deepEqual(keys("UK"), ["authorized_now", "sponsorship_now", "sponsorship_future"]);
  assert.deepEqual(keys("DE"), ["authorized_now", "sponsorship_now", "sponsorship_future"]);
});

test("a market the set does not serve has no questions, never another country's", () => {
  assert.deepEqual(permitFields(ALL, "FR"), []);
  assert.deepEqual(permitQuestions(ALL, "FR"), []);
  assert.deepEqual(permitCount({}, ALL, "FR"), { answered: 0, answerable: 0 });
  assert.deepEqual(permitFields(servedFor(["UK"]), "US"), [], "only the countries you apply in are served");
});

test("each country is asked in its own words, as served", () => {
  const label = (market: string, key: string) => permitQuestions(ALL, market).find((f) => f.key === key)?.label;
  assert.equal(label("US", "authorized_now"), "Authorized to work in the U.S. now?");
  assert.equal(label("UK", "authorized_now"), "Do you have the right to work in the UK now?");
  assert.equal(label("DE", "authorized_now"), "Can you work in this country now?");
  // No US visa word reaches another country.
  for (const market of ["UK", "DE"]) {
    for (const field of permitFields(ALL, market)) assert.doesNotMatch(field.label, /U\.S\.|visa status|H-1B/);
  }
  assert.equal(permitQuestions(ALL, "US")[0], PERMITS.US[0], "the served field, passed through");
});

test("the countries asked are the served set's own, in its order", () => {
  assert.deepEqual(permitMarkets(servedFor(["DE", "US"])), ["DE", "US"]);
  assert.deepEqual(permitMarkets(servedFor(["UK", "DE", "US"])), ["UK", "DE", "US"], "apply-in order, never sorted");
  assert.deepEqual(permitMarkets(servedFor(["UK"])), ["UK"]);
  assert.deepEqual(permitMarkets({ ...ALL, countries: [], chosen: false }), [], "no country chosen asks none");
});

test("a country the set serves no questions for is open, never answered, wherever it is asked", () => {
  const set = servedFor(["US"]);
  assert.equal(permitAnswered({}, set, "UK"), false);
  // Not even with answers stored: without its questions nothing says they are the ones it asks.
  const stored = { work_auth_by_country: { UK: { authorized_now: true, sponsorship_now: false, sponsorship_future: false } } };
  assert.equal(permitAnswered(stored, set, "UK"), false);
  const noQuestions = { ...set, countries: [...set.countries, { market: "UK", label: "United Kingdom", permits: [], answers: [] }] };
  assert.equal(permitAnswered({ work_auth_by_country: { UK: {} } }, noQuestions, "UK"), false);
  // A served country with every answer given is answered; one still blank is not.
  const us = { work_auth_by_country: { US: { status: "citizen", authorized_now: true, sponsorship_now: false, sponsorship_future: false } } };
  assert.equal(permitAnswered(us, set, "US"), true);
  assert.equal(permitAnswered({}, set, "US"), false);
  // Next up asks only what is served, and never skips the served country as answered.
  const missing = missingAnswers({}, set).map(missingKey);
  assert.equal(missing.some((key) => key.startsWith("permit:UK:")), false);
  assert.deepEqual(missing.slice(0, 4), ["permit:US:status", "permit:US:authorized_now", "permit:US:sponsorship_now", "permit:US:sponsorship_future"]);
});

test("the expiry date ends every country's fields and counts toward nothing", () => {
  for (const market of ["US", "UK", "DE"]) {
    assert.equal(permitFields(ALL, market).at(-1)?.key, "authorization_expires_on");
    assert.equal(permitQuestions(ALL, market).some((f) => f.key === "authorization_expires_on"), false);
  }
});

test("a country's answer lands on its own entry, keyed by market, and the others stay", () => {
  const before = { work_auth_by_country: { US: { authorized_now: true } }, custom: [] };
  const after = withPermit(before, ALL, "UK", "sponsorship_now", false);
  assert.deepEqual(after.work_auth_by_country, { US: { authorized_now: true }, UK: { sponsorship_now: false } });
  assert.deepEqual(permitEntry(after, "UK"), { sponsorship_now: false });
  // Clearing removes the key; it is never stored as "".
  assert.deepEqual(permitEntry(withPermit(after, ALL, "UK", "sponsorship_now", undefined), "UK"), {});
});

test("a permit answer that hides another field removes it: a citizen keeps no expiry", () => {
  const before = { work_auth_by_country: { US: { status: "h1b", authorization_expires_on: "2027-01-31" }, UK: { authorized_now: true } } };
  const citizen = withPermit(before, ALL, "US", "status", "citizen");
  assert.deepEqual(permitEntry(citizen, "US"), { status: "citizen" });
  assert.deepEqual(permitEntry(citizen, "UK"), { authorized_now: true }, "another country's answers stay");
  // A status that runs out keeps it.
  assert.deepEqual(permitEntry(withPermit(before, ALL, "US", "status", "h1b"), "US"), before.work_auth_by_country.US);
  // Shown and hidden by the same rule.
  assert.equal(fieldShown(US_EXPIRES, { status: "permanent_resident" }), false);
  assert.equal(fieldShown(US_EXPIRES, { status: "h1b" }), true);
  assert.equal(fieldShown(US_EXPIRES, {}), true);
});

test("a country's own answer lands on its own entry in answers_by_country, and the others stay", () => {
  const before = { answers_by_country: { IN: { current_ctc: "1800000" } }, preferences: { desired_salary: "150000" } };
  const germany = { market: "DE" };
  const after = withCountryAnswer(before, germany, "expected_pay", "70000");
  assert.deepEqual(after.answers_by_country, { IN: { current_ctc: "1800000" }, DE: { expected_pay: "70000" } });
  assert.deepEqual(after.preferences, { desired_salary: "150000" }, "the home's pay is left as it was");
  assert.deepEqual(countryAnswerEntry(withCountryAnswer(after, germany, "expected_pay", ""), germany), {});
  assert.deepEqual(countryAnswerEntry(after, { market: "IN" }), { current_ctc: "1800000" });
});

test("citizenships are saved as codes, each once, and none removes the answer", () => {
  const profile = { personal: { first_name: "Asha" } };
  assert.deepEqual(withCitizenships(profile, ["IN", "GB", "IN"]).personal, { first_name: "Asha", citizenships: ["IN", "GB"] });
  assert.deepEqual(withCitizenships({ personal: { citizenships: ["IN"] } }, []).personal, {});
  // A plain string from an older save still shows, part by part; the picker saves codes in its place.
  assert.deepEqual(citizenshipEntries({ personal: { citizenships: "India, Ireland" } }), ["India", "Ireland"]);
  assert.deepEqual(citizenshipEntries({ personal: { citizenships: ["IN", " ", 7] } }), ["IN"]);
  assert.deepEqual(citizenshipEntries({}), []);
});

// GET /api/countries, a few of them, with the aliases the server's normalize reads (folded).
const CODES = countryCodes([
  { code: "CI", name: "Côte d’Ivoire", aliases: ["ivory coast"] },
  { code: "FR", name: "France" },
  { code: "GB", name: "United Kingdom", aliases: ["uk", "great britain", "england"] },
  { code: "IE", name: "Ireland" },
  { code: "IN", name: "India" },
  { code: "US", name: "United States", aliases: ["usa", "america"] },
]);

test("a country is read by its code in any case, its name or an alias, folded as the server folds it", () => {
  assert.equal(countryCode(CODES, "in"), "IN");
  assert.equal(countryCode(CODES, " India "), "IN");
  assert.equal(countryCode(CODES, "UK"), "GB");
  assert.equal(countryCode(CODES, "USA"), "US");
  assert.equal(countryCode(CODES, "Cote d'Ivoire"), "CI");
  assert.equal(countryCode(CODES, "Narnia"), null);
});

test("a citizenship not held as codes is stored as codes: names, aliases and a code's case, each once", () => {
  // A plain string from an older save or a hand edit.
  assert.deepEqual(withCitizenshipList({ personal: { citizenships: "India, Ireland", city: "Pune" } }, CODES).personal, {
    citizenships: ["IN", "IE"],
    city: "Pune",
  });
  // A list mixing a code and names, "UK" read as GB, the same country once.
  const mixed = { personal: { citizenships: ["IN", "UK", "india"] } };
  assert.equal(citizenshipIsLoose(mixed, CODES), true);
  assert.deepEqual(withCitizenshipList(mixed, CODES).personal, { citizenships: ["IN", "GB"] });
  // An entry that names no country is dropped, as the server's save drops it; with none left, no answer.
  assert.deepEqual(withCitizenshipList({ personal: { citizenships: ["FR", "Narnia"] } }, CODES).personal, { citizenships: ["FR"] });
  assert.deepEqual(withCitizenshipList({ personal: { citizenships: "Narnia" } }, CODES).personal, {});
  // Codes as the picker stores them stay as they are; so does no answer.
  const listed = { personal: { citizenships: ["IN"] } };
  assert.equal(citizenshipIsLoose(listed, CODES), false);
  assert.equal(withCitizenshipList(listed, CODES), listed);
  const none = { personal: { city: "Pune" } };
  assert.equal(withCitizenshipList(none, CODES), none);
  // Before the country list is read, a plain string is stored as its parts (the server turns them into codes),
  // and a list is left for later.
  assert.deepEqual(withCitizenshipList({ personal: { citizenships: "India, Ireland" } }, null).personal, {
    citizenships: ["India", "Ireland"],
  });
  assert.equal(citizenshipIsLoose(mixed, null), false);
});

// An Indian citizen applying in the US and Germany, as the server serves it: nothing settled there. Applying in
// Germany as an EU citizen: the three yes/no answers settled by the French citizenship.
const SETTLED_DE = {
  authorized_now: { value: true, via: "FR" },
  sponsorship_now: { value: false, via: "FR" },
  sponsorship_future: { value: false, via: "FR" },
};
const EU = servedFor(["DE", "US"], { derived: { DE: SETTLED_DE } });
const FRENCH = { personal: { citizenships: ["FR"] } };
const french = (permits: Record<string, unknown>) => ({ ...FRENCH, work_auth_by_country: { DE: permits } });

test("an answer your citizenship settles counts as answered, and next up never asks it", () => {
  assert.equal(permitAnswered(FRENCH, EU, "DE"), true);
  assert.deepEqual(permitCount(FRENCH, EU, "DE"), { answered: 3, answerable: 3 });
  assert.deepEqual(openPermitFields(FRENCH, EU, "DE"), []);
  assert.equal(permitAnswered(FRENCH, EU, "US"), false, "a settled country settles no other");
  assert.deepEqual(openPermitFields(FRENCH, EU, "US").map((f) => f.key), ["status", "authorized_now", "sponsorship_now", "sponsorship_future"]);
  const missing = missingAnswers(FRENCH, EU).map(missingKey);
  assert.equal(missing.some((key) => key.startsWith("permit:DE:")), false);
  assert.equal(missing.includes("permit:US:authorized_now"), true);
  assert.equal(permitAnswers(FRENCH, EU, "DE").authorized_now, true);
});

test("an answer given the same way leaves the rest settled; one that differs settles nothing there", () => {
  const same = french({ authorized_now: "Yes" });
  assert.deepEqual(derivedPermits(same, EU, "DE"), SETTLED_DE);
  assert.equal(permitAnswered(same, EU, "DE"), true);
  assert.equal(differsFromSettled(same, EU, "DE", SETTLED_DE), false);
  const differs = french({ authorized_now: false });
  assert.deepEqual(derivedPermits(differs, EU, "DE"), {});
  assert.equal(differsFromSettled(differs, EU, "DE", SETTLED_DE), true);
  assert.deepEqual(permitCount(differs, EU, "DE"), { answered: 1, answerable: 3 });
  assert.deepEqual(openPermitFields(differs, EU, "DE").map((f) => f.key), ["sponsorship_now", "sponsorship_future"]);
  assert.deepEqual(
    missingAnswers(differs, EU).map(missingKey).filter((key) => key.startsWith("permit:DE:")),
    ["permit:DE:sponsorship_now", "permit:DE:sponsorship_future"],
  );
  // The fill reads what you gave over what is settled.
  assert.equal(permitAnswers(differs, EU, "DE").authorized_now, false);
  // A blank or unusable answer is no answer: it hides nothing.
  assert.deepEqual(derivedPermits(french({ authorized_now: "maybe" }), EU, "DE"), SETTLED_DE);
});

test("removing the citizenship stops what it settled before the questions are read again", () => {
  // The served set still says the French citizenship settles Germany; the profile on screen no longer lists it.
  assert.deepEqual(derivedPermits({ personal: { citizenships: ["IN"] } }, EU, "DE"), {});
  assert.deepEqual(derivedPermits({}, EU, "DE"), {});
  assert.equal(permitAnswered({}, EU, "DE"), false);
  assert.deepEqual(openPermitFields({}, EU, "DE").map((f) => f.key), ["authorized_now", "sponsorship_now", "sponsorship_future"]);
  // A code in another case is the same citizenship; and it only narrows: nothing the server did not settle.
  assert.deepEqual(derivedPermits({ personal: { citizenships: ["fr"] } }, EU, "DE"), SETTLED_DE);
  assert.deepEqual(derivedPermits(FRENCH, EU, "US"), {});
  // A differing answer under a citizenship you removed differs from nothing.
  assert.equal(differsFromSettled({ work_auth_by_country: { DE: { authorized_now: false } } }, EU, "DE", SETTLED_DE), false);
});

test("a citizenship held by name is not answered once the country list is read, so next up asks it first", () => {
  // A hand edit left names: they settle nothing here, so citizenship is asked again and Next stores codes.
  const named = { personal: { citizenships: ["France", "IE"] } };
  const set = servedFor(["DE"]);
  const withCitizenship: QuestionSet = {
    ...set,
    groups: set.groups.map((group) =>
      group.key === "personal"
        ? { ...group, fields: [...group.fields, { key: "citizenships", label: "Citizen of", type: "countries" as const }] }
        : group,
    ),
  };
  assert.equal(citizenshipAnswered(named, withCitizenship, CODES), false);
  assert.equal(missingAnswers(named, withCitizenship, CODES).map(missingKey)[0], "citizenship");
  // Before the list is read it cannot tell, so it counts as given; codes count either way.
  assert.equal(citizenshipAnswered(named, withCitizenship, null), true);
  assert.equal(citizenshipAnswered({ personal: { citizenships: ["FR", "IE"] } }, withCitizenship, CODES), true);
  assert.equal(missingAnswers({ personal: { citizenships: ["FR"] } }, withCitizenship, CODES).map(missingKey).includes("citizenship"), false);
});

test("a citizenship held by name settles nothing on screen until it is stored as codes, then what it should", () => {
  const named = { personal: { citizenships: ["France"] } };
  assert.deepEqual(derivedPermits(named, EU, "DE"), {});
  // Next up and Setup store it as codes first, so what the server settles applies on screen too.
  const coded = withCitizenshipList({ personal: { citizenships: "France" } }, CODES);
  assert.deepEqual(coded.personal, { citizenships: ["FR"] });
  assert.deepEqual(derivedPermits(coded, EU, "DE"), SETTLED_DE);
  assert.deepEqual(openPermitFields(coded, EU, "DE"), []);
  assert.equal(missingAnswers(coded, EU).map(missingKey).some((key) => key.startsWith("permit:DE:")), false);
});

test("a status your citizenship settles hides the expiry, as a status you gave does", () => {
  const us = servedFor(["US"], { derived: { US: { status: { value: "citizen", via: "US" } } } });
  const american = { personal: { citizenships: ["US"] } };
  const shown = permitFields(us, "US").filter((field) => fieldShown(field, permitAnswers(american, us, "US")));
  assert.equal(shown.some((field) => field.key === "authorization_expires_on"), false);
});

test("a country your citizenship settles is not asked when the permit runs out: that right does not", () => {
  const keys = (profile: Parameters<typeof shownPermitFields>[0], answering: string[] = []) =>
    shownPermitFields(profile, EU, "DE", answering).map((f) => f.key);
  const asked = ["authorized_now", "sponsorship_now", "sponsorship_future"];
  assert.deepEqual(keys(FRENCH), asked);
  // Answering one yourself, an answer that differs, or no citizenship there: the expiry is asked again.
  assert.deepEqual(keys(FRENCH, ["authorized_now"]), [...asked, "authorization_expires_on"]);
  assert.deepEqual(keys(french({ authorized_now: false })), [...asked, "authorization_expires_on"]);
  assert.deepEqual(keys({}), [...asked, "authorization_expires_on"]);
  // A stored expiry always shows.
  assert.deepEqual(keys(french({ authorization_expires_on: "2027-01-31" })), [...asked, "authorization_expires_on"]);
  // Another country's expiry is its own.
  assert.equal(shownPermitFields(FRENCH, EU, "US").some((f) => f.key === "authorization_expires_on"), true);
});

test("each language asks the served fields too, each select with a way back to Not set", () => {
  const cefr: FieldDef = select("cefr", "Level (CEFR)", ["A1", "B2", "C2"]);
  const fields = languageFields({ ...ALL, language_fields: [{ ...cefr, optional: true }] });
  assert.deepEqual(fields.map((f) => f.key), ["language", "read", "speak", "write", "native", "fluent", "cefr"]);
  assert.deepEqual(fields.at(-1)?.options?.map((o) => o.value), ["not_set", "A1", "B2", "C2"]);
  assert.deepEqual(languageFields(ALL).map((f) => f.key), ["language", "read", "speak", "write", "native", "fluent"]);
});

test("a number is answered by a number or by what was typed", () => {
  const years: FieldDef = { key: "experience_years", label: "Total experience: years", type: "number", optional: true };
  assert.equal(answered(years, 6), true);
  assert.equal(answered(years, 0), true);
  assert.equal(answered(years, "6"), true);
  // A number box sends text: "0" is an answer, as the server reads it (0 days, never a blank).
  assert.equal(answered(years, "0"), true);
  assert.equal(answered(years, ""), false);
  assert.equal(answered(years, Number.NaN), false);
});

test("editing reads each country's legacy pair as typed answers, and a save sends no one-set view", () => {
  const served = {
    work_auth: { authorized_to_work: "yes" },
    work_auth_market: "US",
    work_auth_by_country: {
      US: { authorized_to_work: "yes", requires_sponsorship: "no" },
      UK: { authorized_now: "Yes", sponsorship_future: "no" },
    },
  };
  const editing = profileForEditing(served);
  assert.equal("work_auth" in editing, false);
  // The legacy sponsorship flag answers only the future question; the present one stays unknown.
  assert.deepEqual(permitEntry(editing, "US"), { authorized_now: true, sponsorship_future: false });
  // The Companion's pause row types "Yes": it reads as the answer.
  assert.deepEqual(permitEntry(editing, "UK"), { authorized_now: true, sponsorship_future: false });
  assert.equal("work_auth" in forSaving(served), false);
  assert.equal("work_auth_market" in forSaving(served), false, "the one set's marker goes with it");
  assert.equal("work_auth_market" in editing, false);
});

test("answered: a boolean needs a yes or no, a select one of its options, text any words", () => {
  const [status, authorized] = permitQuestions(ALL, "US");
  assert.equal(answered(status, "citizen"), true);
  assert.equal(answered(status, "OPT"), false);
  assert.equal(answered(authorized, false), true);
  assert.equal(answered(authorized, "No"), true);
  assert.equal(answered(authorized, ""), false);
  assert.equal(answered({ key: "email", label: "Email" }, "  "), false);
});

test("a self-description goes with the answer it belongs to", () => {
  const described = withField(
    withField({}, ALL, "eeo", "gender", "self_describe"),
    ALL,
    "eeo",
    "gender_self_describe",
    "Agender",
  );
  assert.equal((described.eeo as Record<string, unknown>).gender_self_describe, "Agender");
  const changed = withField(described, ALL, "eeo", "gender", "female");
  assert.equal("gender_self_describe" in (changed.eeo as Record<string, unknown>), false);
});

test("decline the rest declines every blank diversity select, the veteran question too", () => {
  const declines = declinedEeo({ eeo: { gender: "female" } }, ALL);
  assert.deepEqual(declines, { veteran_status: "decline", disability_status: "decline", hispanic_latino: "decline" });
  assert.deepEqual(declinedEeo({ eeo: { ...declines, gender: "male" } }, ALL), {});
});

// The market list (GET /api/settings/market `markets`): which markets have a checked diversity set.
const MARKETS: MarketOption[] = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false },
  { key: "IN", label: "India", country_code: "IN", currency: "INR", date_format: "DMY", offers_eeo: false },
  { key: "AE", label: "United Arab Emirates", country_code: "AE", currency: "AED", date_format: "DMY", offers_eeo: false },
  { key: "NL", label: "Netherlands", country_code: "NL", currency: "EUR", date_format: "DMY", offers_eeo: false },
];

test("diversity names the served countries with a checked set, and none while no country is chosen", () => {
  // Unchosen: the market setting still stores the US, but the served set lists no country and offers none.
  const unchosen: QuestionSet = { ...servedFor([], { offersEeo: false }), chosen: false };
  assert.deepEqual(diversityCountries(unchosen, MARKETS), []);
  assert.deepEqual(diversityCountries(servedFor(["US"]), MARKETS), ["United States"]);
  // In the order you apply in, only the countries with a set.
  assert.deepEqual(diversityCountries(servedFor(["DE", "UK", "US"]), MARKETS), ["United Kingdom", "United States"]);
  const india: QuestionSet = {
    ...servedFor([], { offersEeo: false }),
    countries: MARKETS.filter((m) => ["IN", "AE", "DE", "NL"].includes(m.key)).map((m) => ({
      market: m.key,
      label: m.label,
      permits: [],
      answers: [],
    })),
  };
  assert.deepEqual(diversityCountries(india, MARKETS), []);
  // The served set decides: one that offers none names none, whatever the market list says.
  assert.deepEqual(diversityCountries(servedFor(["US"], { offersEeo: false }), MARKETS), []);
  assert.deepEqual(diversityCountries(servedFor(["US"]), []), [], "a market the list lacks has no set");
});

test("a group's fields are the served group's, by key; a group the set lacks has none", () => {
  assert.equal(groupFields(ALL, "eeo"), ALL.groups[1].fields);
  assert.deepEqual(groupFields(ALL, "contact"), []);
});

test("counts are the required answers only, per group and per country", () => {
  const profile = {
    personal: { first_name: "Ada", address_2: "Flat 2" },
    work_auth_by_country: { US: { status: "citizen", authorized_now: true }, UK: { authorized_now: "No" } },
  };
  assert.deepEqual(groupCount(profile, ALL, "personal"), { answered: 1, answerable: 4 },
    "address line 2 and the three links are optional");
  assert.deepEqual(permitCount(profile, ALL, "US"), { answered: 2, answerable: 4 });
  assert.deepEqual(permitCount(profile, ALL, "UK"), { answered: 1, answerable: 3 });
  assert.deepEqual(permitCount(profile, ALL, "DE"), { answered: 0, answerable: 3 });
});

test("next up asks each country's permit first, then contact, then start and pay, then diversity", () => {
  const full = {
    personal: Object.fromEntries(groupFields(ALL, "personal").map((f) => [f.key, "x"])),
    preferences: { desired_salary: "x", willing_to_relocate: false },
  };
  // The set served for those countries: Germany alone has no checked diversity set.
  const keysOf = (profile: Parameters<typeof missingAnswers>[0], applyIn: string[]) =>
    missingAnswers(profile, servedFor(applyIn, { offersEeo: applyIn.includes("US") })).map(missingKey);
  assert.deepEqual(keysOf(full, ["DE", "US"]), [
    "permit:DE:authorized_now", "permit:DE:sponsorship_now", "permit:DE:sponsorship_future",
    "permit:US:status", "permit:US:authorized_now", "permit:US:sponsorship_now", "permit:US:sponsorship_future",
    "diversity",
  ]);
  // Germany alone has no checked diversity set: nothing asks it.
  assert.equal(keysOf(full, ["DE"]).includes("diversity"), false);
  const some = { personal: { first_name: "Ada" }, work_auth_by_country: { DE: { authorized_now: true, sponsorship_now: false, sponsorship_future: false } } };
  assert.deepEqual(keysOf(some, ["DE"]).slice(0, 2), ["personal:last_name", "personal:email"]);
  assert.equal(keysOf(some, ["DE"]).includes("personal:address_2"), false, "an optional field is never next up");
  for (const link of ["linkedin", "github", "website"]) {
    assert.equal(keysOf(some, ["DE"]).includes(`personal:${link}`), false, `${link} is optional, never next up`);
  }
});

// The state line, as the server resolves it for where you live (markets.yaml `asks_state` and `state_label`).
const PROVINCE: FieldDef = { key: "state", label: "Province", byHome: "state" };
const NO_STATE: FieldDef = { key: "state", label: "Province", byHome: "state", optional: true };

test("the state line reads as served: its home's word, and optional where addresses have none", () => {
  const state = (served: FieldDef) => groupFields(servedFor(["DE"], { state: served }), "personal").find((f) => f.key === "state");
  assert.deepEqual([state(PROVINCE)?.label, Boolean(state(PROVINCE)?.optional)], ["Province", false]);
  assert.deepEqual([state(NO_STATE)?.label, state(NO_STATE)?.optional], ["Province", true]);
});

test("contact counts the state only where it is served as required", () => {
  const profile = { personal: { first_name: "Sam" } };
  assert.deepEqual(groupCount(profile, servedFor(["DE"], { state: NO_STATE }), "personal"), { answered: 1, answerable: 3 });
  assert.deepEqual(groupCount(profile, servedFor(["DE"], { state: STATE }), "personal"), { answered: 1, answerable: 4 });
});

// Citizenship, served in the personal group: Country answers asks it, and setup readiness counts it beside the
// work permits it settles.
const CITIZEN: FieldDef = { key: "citizenships", label: "Citizen of", type: "countries" };

function withCitizenship(served: QuestionSet): QuestionSet {
  return {
    ...served,
    groups: served.groups.map((g) => (g.key === "personal" ? { ...g, fields: [...g.fields, CITIZEN] } : g)),
  };
}

test("contact leaves citizenship to Country answers: it neither shows nor counts it", () => {
  const served = withCitizenship(servedFor(["DE"]));
  assert.deepEqual(contactFields(served), groupFields(servedFor(["DE"]), "personal"));
  const profile = { personal: { first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", state: "BE" } };
  assert.deepEqual(groupCount(profile, served, "personal"), { answered: 4, answerable: 4 });
});

test("next up asks citizenship first, with its picker, never in a text box", () => {
  const served = withCitizenship(servedFor(["DE"], { offersEeo: false }));
  const done = { authorized_now: true, sponsorship_now: false, sponsorship_future: false };
  const personal = { first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", state: "BE" };
  const profile = {
    personal,
    work_auth_by_country: { DE: done },
    preferences: { desired_salary: "x", willing_to_relocate: false },
  };
  const [first, ...rest] = missingAnswers(profile, served);
  assert.deepEqual([first.kind, first.kind === "citizenship" && first.field.key, rest], ["citizenship", "citizenships", []]);
  assert.equal(missingAnswers({}, served).map(missingKey)[0], "citizenship", "before every country's permits");
  const citizen = { ...profile, personal: { ...personal, citizenships: ["IN"] } };
  assert.deepEqual(missingAnswers(citizen, served).map(missingKey), []);
  // A plain string names no list: still asked, as setup readiness counts it.
  const loose = { ...profile, personal: { ...personal, citizenships: "India" } };
  assert.deepEqual(missingAnswers(loose, served).map(missingKey), ["citizenship"]);
});

test("next up asks where you apply first while no country is chosen, and never once one is", () => {
  // Unchosen, no country's permits are asked, so every other answer can be given while every form pauses on them.
  const unchosen: QuestionSet = { ...withCitizenship(servedFor([], { offersEeo: false })), chosen: false };
  const personal = { first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", state: "BE", citizenships: ["IN"] };
  const profile = { personal, preferences: { desired_salary: "x", willing_to_relocate: false } };
  assert.deepEqual(missingAnswers(profile, unchosen).map(missingKey), ["where"]);
  assert.deepEqual(missingAnswers({}, unchosen).map(missingKey).slice(0, 2), ["where", "citizenship"]);
  assert.deepEqual(missingAnswers(profile, withCitizenship(servedFor(["DE"], { offersEeo: false }))).map(missingKey),
    ["permit:DE:authorized_now", "permit:DE:sponsorship_now", "permit:DE:sponsorship_future"]);
});

test("a list of countries is answered once it holds one", () => {
  assert.equal(answered(CITIZEN, ["IN"]), true);
  assert.equal(answered(CITIZEN, ["IN", "FR"]), true);
  for (const value of [[], [""], ["  "], "India", undefined, null, [7]]) {
    assert.equal(answered(CITIZEN, value), false, JSON.stringify(value));
  }
});

test("next up asks the state where it is required, never where it is served optional", () => {
  const missing = (state: FieldDef) =>
    missingAnswers({ personal: { first_name: "Sam" } }, servedFor(["DE"], { state })).map(missingKey);
  assert.equal(missing(NO_STATE).includes("personal:state"), false);
  assert.equal(missing(STATE).includes("personal:state"), true);
  const province = missingAnswers({}, servedFor(["DE"], { state: PROVINCE })).find((m) => missingKey(m) === "personal:state");
  assert.equal(province?.kind === "field" && province.field.label, "Province");
});

// Someone who lives in the United States and applies there and in Germany, as served: the home's set asks its pay
// (`home`, required, read from the desired salary, so Start and pay no longer lists it), Germany's own pay is
// optional, and notice is one answer in days whose older words (`notice_period`) still answer it.
const NOTICE: FieldDef = { key: "notice_days", label: "Notice period", type: "number", legacy: "notice_period" };
const RELOCATE = yesNo("willing_to_relocate", "Willing to relocate?");
const HOME_SET: QuestionSet = (() => {
  const set = withCitizenship(servedFor(["US", "DE"], { offersEeo: false }));
  return {
    ...set,
    groups: set.groups.map((g) => (g.key === "preferences" ? { ...g, fields: [NOTICE, RELOCATE] } : g)),
    countries: set.countries.map((country) =>
      country.market === "US"
        ? { ...country, home: true, answers: [{ key: "expected_pay", label: "Expected salary (USD)" }] }
        : { ...country, answers: [{ key: "expected_pay", label: "Expected salary (EUR)", optional: true }] },
    ),
  };
})();
const [US_HOME, GERMANY] = HOME_SET.countries;
const US_PERMITS = { status: "citizen", authorized_now: true, sponsorship_now: false, sponsorship_future: false };

test("the home's pay is read and written as the desired salary; another country's as its own entry", () => {
  const profile = {
    preferences: { desired_salary: "$80,000", notice_days: 14 },
    answers_by_country: { DE: { expected_pay: "€60,000" } },
  };
  assert.deepEqual(countryAnswerEntry(profile, US_HOME), { expected_pay: "$80,000" });
  assert.deepEqual(countryAnswerEntry(profile, GERMANY), { expected_pay: "€60,000" });
  const raised = withCountryAnswer(profile, US_HOME, "expected_pay", "$90,000");
  assert.deepEqual(raised.preferences, { desired_salary: "$90,000", notice_days: 14 });
  assert.deepEqual(raised.answers_by_country, { DE: { expected_pay: "€60,000" } }, "no home entry is written");
  const german = withCountryAnswer(profile, GERMANY, "expected_pay", "€65,000");
  assert.deepEqual(german.answers_by_country, { DE: { expected_pay: "€65,000" } });
  assert.deepEqual(german.preferences, profile.preferences, "the home's pay is left as it was");
  // Cleared, the home's pay goes, as any country's own answer does; the other preferences stay.
  assert.deepEqual(withCountryAnswer(profile, US_HOME, "expected_pay", "").preferences, { notice_days: 14 });
  assert.deepEqual(countryAnswerEntry({}, US_HOME), {});
});

test("a country is done once its permits and its required answers are: the home's pay is in its set", () => {
  const noPay = { personal: { citizenships: ["IN"] }, work_auth_by_country: { US: US_PERMITS } };
  // Setup's work-permit step asks no pay (Decision 8): the permits alone are still answered.
  assert.equal(permitAnswered(noPay, HOME_SET, "US"), true);
  assert.deepEqual(countryAnswersOpen(noPay, HOME_SET, "US").map((f) => f.key), ["expected_pay"]);
  assert.equal(countryAnswered(noPay, HOME_SET, "US"), false);
  assert.deepEqual(countryCount(noPay, HOME_SET, "US"), { answered: 4, answerable: 5 });
  const paid = { ...noPay, preferences: { desired_salary: "$80,000" } };
  assert.deepEqual(countryAnswersOpen(paid, HOME_SET, "US"), []);
  assert.equal(countryAnswered(paid, HOME_SET, "US"), true);
  assert.deepEqual(countryCount(paid, HOME_SET, "US"), { answered: 5, answerable: 5 });
  // Another country's pay is optional, so it is never open; a country the set lacks has nothing of its own.
  assert.deepEqual(countryAnswersOpen({}, HOME_SET, "DE"), []);
  assert.deepEqual(countryCount({}, HOME_SET, "DE"), permitCount({}, HOME_SET, "DE"));
  assert.deepEqual(countryAnswersOpen({}, HOME_SET, "FR"), []);
  assert.equal(countryAnswered({}, HOME_SET, "FR"), false);
});

test("next up asks the home's pay after its permits and before the next country's", () => {
  const missing = missingAnswers({}, HOME_SET);
  assert.deepEqual(missing.map(missingKey).slice(0, 7), [
    "citizenship",
    "permit:US:status", "permit:US:authorized_now", "permit:US:sponsorship_now", "permit:US:sponsorship_future",
    "answer:US:expected_pay",
    "permit:DE:authorized_now",
  ]);
  const pay = missing.find((item) => missingKey(item) === "answer:US:expected_pay");
  assert.deepEqual(pay?.kind === "answer" && [pay.market, pay.field.label], ["US", "Expected salary (USD)"]);
  // Germany's own pay is optional: never next up.
  assert.equal(missing.map(missingKey).some((key) => key.startsWith("answer:DE:")), false);
  // Given, as the desired salary, it is not asked.
  const paid = missingAnswers({ preferences: { desired_salary: "$80,000" } }, HOME_SET).map(missingKey);
  assert.equal(paid.includes("answer:US:expected_pay"), false);
});

test("notice written in words before still answers it in days: counted as set, and never asked", () => {
  const legacy = { preferences: { notice_period: "negotiable", willing_to_relocate: false } };
  assert.equal(answeredIn(NOTICE, legacy.preferences), true);
  assert.deepEqual(groupCount(legacy, HOME_SET, "preferences"), { answered: 2, answerable: 2 });
  assert.equal(missingAnswers(legacy, HOME_SET).map(missingKey).includes("preferences:notice_days"), false);
  // Days answer it, 0 included, stored as a number or typed into the box as text.
  for (const days of [0, 14, "0", "14"]) assert.equal(answeredIn(NOTICE, { notice_days: days }), true, String(days));
  // Blank words are no answer, and a field with no older key is answered by its own value only.
  assert.equal(answeredIn(NOTICE, { notice_period: "  " }), false);
  assert.equal(answeredIn(RELOCATE, { notice_period: "negotiable" }), false);
  assert.deepEqual(groupCount({ preferences: {} }, HOME_SET, "preferences"), { answered: 0, answerable: 2 });
  assert.equal(missingAnswers({}, HOME_SET).map(missingKey).includes("preferences:notice_days"), true);
});

test("next up reads and writes each answer where its list keeps it: the home's pay as the desired salary", () => {
  const profile = { personal: { citizenships: ["IN"] }, preferences: { notice_days: 14 } };
  const asked = (key: string) => {
    const item = missingAnswers(profile, HOME_SET).find((m) => missingKey(m) === key);
    assert.ok(item && item.kind !== "where" && item.kind !== "citizenship" && item.kind !== "diversity", key);
    return item;
  };
  const pay = asked("answer:US:expected_pay");
  assert.equal(missingValue(profile, HOME_SET, pay), undefined);
  const paid = withMissingAnswer(profile, HOME_SET, pay, "$80,000");
  assert.deepEqual(paid.preferences, { notice_days: 14, desired_salary: "$80,000" });
  assert.equal("answers_by_country" in paid, false, "no home entry is written");
  assert.equal(missingValue(paid, HOME_SET, pay), "$80,000");
  const permit = asked("permit:DE:authorized_now");
  assert.deepEqual(permitEntry(withMissingAnswer(profile, HOME_SET, permit, true), "DE"), { authorized_now: true });
  const relocate = asked("preferences:willing_to_relocate");
  const moved = withMissingAnswer(profile, HOME_SET, relocate, false);
  assert.equal(missingValue(moved, HOME_SET, relocate), false);
});
