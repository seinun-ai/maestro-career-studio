import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answered,
  citizenshipEntries,
  contactFields,
  countryAnswerEntry,
  declinedEeo,
  derivedPermits,
  differsFromSettled,
  fieldShown,
  forSaving,
  groupCount,
  groupFields,
  languageFields,
  missingAnswers,
  missingKey,
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
  withPermit,
} from "./autofill-options.ts";
import type { DerivedAnswer, FieldDef, QuestionSet } from "./types.ts";

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
  const after = withCountryAnswer(before, "DE", "expected_pay", "70000");
  assert.deepEqual(after.answers_by_country, { IN: { current_ctc: "1800000" }, DE: { expected_pay: "70000" } });
  assert.deepEqual(after.preferences, { desired_salary: "150000" }, "the generic pay is left as it was");
  assert.deepEqual(countryAnswerEntry(withCountryAnswer(after, "DE", "expected_pay", ""), "DE"), {});
  assert.deepEqual(countryAnswerEntry(after, "IN"), { current_ctc: "1800000" });
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

test("a citizenship stored as a plain string is stored as a list of its parts; a list stays as it is", () => {
  assert.deepEqual(withCitizenshipList({ personal: { citizenships: "India, Ireland", city: "Pune" } }).personal, {
    citizenships: ["India", "Ireland"],
    city: "Pune",
  });
  const listed = { personal: { citizenships: ["IN"] } };
  assert.equal(withCitizenshipList(listed), listed);
  const none = { personal: { city: "Pune" } };
  assert.equal(withCitizenshipList(none), none);
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
