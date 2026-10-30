import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answered,
  contactCount,
  contactFields,
  declinedEeo,
  forSaving,
  groupCount,
  groupFields,
  missingAnswers,
  missingKey,
  permitCount,
  permitAnswered,
  permitEntry,
  permitFields,
  permitMarkets,
  permitQuestions,
  profileForEditing,
  withField,
  withPermit,
} from "./autofill-options.ts";
import type { FieldDef, QuestionSet } from "./types.ts";

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
const PERMITS: Record<string, FieldDef[]> = {
  US: [
    select("status", "Work authorization status", ["citizen", "h1b"]),
    yesNo("authorized_now", "Authorized to work in the U.S. now?"),
    yesNo("sponsorship_now", "Do you need visa sponsorship now?"),
    yesNo("sponsorship_future", "Will you need visa sponsorship later?"),
    EXPIRES,
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
const STATE: FieldDef = { key: "state", label: "State", byHome: true };

/** The set for `applyIn`, with the state line as the server resolved it for where you live. */
function servedFor(applyIn: string[], { state = STATE, offersEeo = true } = {}): QuestionSet {
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
    permits: Object.fromEntries(applyIn.map((market) => [market, PERMITS[market]])),
    offers_eeo: offersEeo,
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
  assert.deepEqual(permitMarkets(servedFor(["UK"])), ["UK"]);
});

test("a country the set serves no questions for is open, never answered, wherever it is asked", () => {
  const set = servedFor(["US"]);
  assert.equal(permitAnswered({}, set, "UK"), false);
  // Not even with answers stored: without its questions nothing says they are the ones it asks.
  const stored = { work_auth_by_country: { UK: { authorized_now: true, sponsorship_now: false, sponsorship_future: false } } };
  assert.equal(permitAnswered(stored, set, "UK"), false);
  assert.equal(permitAnswered({ work_auth_by_country: { UK: {} } }, { ...set, permits: { ...set.permits, UK: [] } }, "UK"), false);
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
    assert.equal(permitFields(ALL, market).at(-1), EXPIRES);
    assert.equal(permitQuestions(ALL, market).some((f) => f.key === "authorization_expires_on"), false);
  }
});

test("a country's answer lands on its own entry, keyed by market, and the others stay", () => {
  const before = { work_auth_by_country: { US: { authorized_now: true } }, custom: [] };
  const after = withPermit(before, "UK", "sponsorship_now", false);
  assert.deepEqual(after.work_auth_by_country, { US: { authorized_now: true }, UK: { sponsorship_now: false } });
  assert.deepEqual(permitEntry(after, "UK"), { sponsorship_now: false });
  // Clearing removes the key; it is never stored as "".
  assert.deepEqual(permitEntry(withPermit(after, "UK", "sponsorship_now", undefined), "UK"), {});
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
const PROVINCE: FieldDef = { key: "state", label: "Province", byHome: true };
const NO_STATE: FieldDef = { key: "state", label: "Province", byHome: true, optional: true };

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

test("contact leaves citizenship to Country answers: it neither shows nor counts it", () => {
  const citizen: FieldDef = { key: "citizenships", label: "Citizen of", type: "countries" };
  const plain = servedFor(["DE"]);
  const served: QuestionSet = {
    ...plain,
    groups: plain.groups.map((g) => (g.key === "personal" ? { ...g, fields: [...g.fields, citizen] } : g)),
  };
  assert.deepEqual(contactFields(served), groupFields(plain, "personal"));
  const profile = { personal: { first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", state: "BE" } };
  assert.deepEqual(contactCount(profile, served), { answered: 4, answerable: 4 });
  // The group still holds it: setup readiness counts citizenship in `personal`.
  assert.deepEqual(groupCount(profile, served, "personal"), { answered: 4, answerable: 5 });
});

test("next up asks the state where it is required, never where it is served optional", () => {
  const missing = (state: FieldDef) =>
    missingAnswers({ personal: { first_name: "Sam" } }, servedFor(["DE"], { state })).map(missingKey);
  assert.equal(missing(NO_STATE).includes("personal:state"), false);
  assert.equal(missing(STATE).includes("personal:state"), true);
  const province = missingAnswers({}, servedFor(["DE"], { state: PROVINCE })).find((m) => missingKey(m) === "personal:state");
  assert.equal(province?.kind === "field" && province.field.label, "Province");
});
