import assert from "node:assert/strict";
import { test } from "node:test";

import {
  GROUPS,
  US_WORK_STATUS,
  answered,
  declinedEeo,
  forSaving,
  groupCount,
  missingAnswers,
  missingKey,
  permitCount,
  permitEntry,
  permitQuestions,
  permitVocab,
  profileForEditing,
  withField,
  withPermit,
  workPermitFields,
} from "./autofill-options.ts";

const keys = (vocab: string | undefined) => permitQuestions(vocab).map((f) => f.key);

test("every vocabulary asks the three keys; only us_visa asks the visa status, first", () => {
  assert.deepEqual(keys("us_visa"), ["status", "authorized_now", "sponsorship_now", "sponsorship_future"]);
  assert.deepEqual(keys("uk"), ["authorized_now", "sponsorship_now", "sponsorship_future"]);
  assert.deepEqual(keys("generic"), ["authorized_now", "sponsorship_now", "sponsorship_future"]);
});

test("an unknown or missing vocabulary reads as generic, never as the US one", () => {
  assert.equal(permitVocab("fr_titre"), "generic");
  assert.equal(permitVocab(undefined), "generic");
  assert.deepEqual(keys(null), keys("generic"));
});

test("each country is asked in its own words", () => {
  const label = (vocab: string, key: string) => permitQuestions(vocab).find((f) => f.key === key)?.label;
  assert.equal(label("us_visa", "authorized_now"), "Authorized to work in the U.S. now?");
  assert.equal(label("uk", "authorized_now"), "Do you have the right to work in the UK now?");
  assert.equal(label("generic", "authorized_now"), "Can you work in this country now?");
  // No US visa word reaches another country.
  for (const vocab of ["uk", "generic"]) {
    for (const field of permitQuestions(vocab)) assert.doesNotMatch(field.label, /U\.S\.|visa status|H-1B/);
  }
  const status = permitQuestions("us_visa")[0];
  assert.equal(status.type, "select");
  assert.equal(status.options, US_WORK_STATUS);
  assert.ok(permitQuestions("uk").every((f) => f.boolean === true));
});

test("the expiry date is asked for every country and counts toward nothing", () => {
  for (const vocab of ["us_visa", "uk", "generic"]) {
    const last = workPermitFields(vocab).at(-1);
    assert.equal(last?.key, "authorization_expires_on");
    assert.equal(last?.optional, true);
    assert.equal(last?.type, "date");
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
  const [status, authorized] = permitQuestions("us_visa");
  assert.equal(answered(status, "citizen"), true);
  assert.equal(answered(status, "OPT"), false);
  assert.equal(answered(authorized, false), true);
  assert.equal(answered(authorized, "No"), true);
  assert.equal(answered(authorized, ""), false);
  assert.equal(answered({ key: "email", label: "Email" }, "  "), false);
});

test("a self-description goes with the answer it belongs to", () => {
  const described = withField(withField({}, "eeo", "gender", "self_describe"), "eeo", "gender_self_describe", "Agender");
  assert.equal((described.eeo as Record<string, unknown>).gender_self_describe, "Agender");
  const changed = withField(described, "eeo", "gender", "female");
  assert.equal("gender_self_describe" in (changed.eeo as Record<string, unknown>), false);
});

test("decline the rest declines every blank diversity select, the veteran question too", () => {
  const declines = declinedEeo({ eeo: { gender: "female" } });
  assert.deepEqual(declines, { veteran_status: "decline", disability_status: "decline", hispanic_latino: "decline" });
  assert.deepEqual(declinedEeo({ eeo: { ...declines, gender: "male" } }), {});
});

test("the groups the readiness count mirrors are all here", () => {
  assert.deepEqual(GROUPS.map((g) => g.key), ["personal", "eeo", "eligibility", "preferences"]);
});

test("counts are the required answers only, per group and per country", () => {
  const profile = {
    personal: { first_name: "Ada", address_2: "Flat 2" },
    work_auth_by_country: { US: { status: "citizen", authorized_now: true }, UK: { authorized_now: "No" } },
  };
  const counts = (p: Parameters<typeof groupCount>[0]) => groupCount(p, "personal");
  assert.deepEqual(counts(profile), { answered: 1, answerable: 12 }, "address line 2 is optional");
  assert.deepEqual(permitCount(profile, "US", "us_visa"), { answered: 2, answerable: 4 });
  assert.deepEqual(permitCount(profile, "UK", "uk"), { answered: 1, answerable: 3 });
  assert.deepEqual(permitCount(profile, "DE", "generic"), { answered: 0, answerable: 3 });
});

test("next up asks each country's permit first, then contact, then start and pay, then diversity", () => {
  const markets = [
    { key: "US", work_auth_vocab: "us_visa", offers_eeo: true },
    { key: "DE", work_auth_vocab: "generic", offers_eeo: false },
  ];
  const full = {
    personal: Object.fromEntries(GROUPS[0].fields.map((f) => [f.key, "x"])),
    preferences: { desired_salary: "x", notice_period: "x", earliest_start_date: "x", willing_to_relocate: false, how_heard: "x" },
  };
  const keysOf = (profile: Parameters<typeof missingAnswers>[0], applyIn: string[]) =>
    missingAnswers(profile, applyIn, markets).map(missingKey);
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
});
