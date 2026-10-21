// Profile rendered with seeded reads (design refresh, Task 7.2). pytest runs it:
// backend/tests/test_frontend_profile_tiles.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement, withRouter } from "../render-harness.mjs";

const { ProfileView } = load("components/profile/profile-view.tsx");

// The one filled button's classes (components/ui/button.tsx, variant "default").
const FILLED = /bg-primary text-primary-foreground/g;

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true, work_auth_vocab: "us_visa" },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true, work_auth_vocab: "uk" },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
];
const group = (answered, answerable) => ({ answered, answerable });
const STATUS = {
  model_key: { done: true, detail: {} },
  import_resumes: { done: true, detail: {} },
  autofill: {
    done: false,
    readiness: 0.5,
    groups: { personal: group(12, 12), work_auth: group(0, 10), preferences: group(1, 5), eeo: group(0, 4) },
    blocking: ["work_auth"],
    work_auth_by_country: {},
  },
  job_preferences: { done: true, detail: {} },
  persona: { done: false, detail: {} },
  template: { done: true, detail: {} },
  engines: { pdflatex: { available: true, warning: null }, typst: { available: true, warning: null } },
  suggested_bases: [],
  complete: false,
};
const CONSENT = { enabled: false, consent_forms: false, acknowledged_at: null, policy_version: "2" };
const PREFS = {
  favored_roles: [{ role: null, label: "Product designer", category: null }],
  role_categories: [],
  years_experience: 6,
  employment_types: [],
  locations: [],
  remote: "hybrid",
  min_salary: null,
  notes: null,
};
const RESUMES = [
  { slug: "uk-design", display_name: "Product designer (UK)", role_category: "design", role_label: null, pdf_rendered_at: null,
    updated_at: "2026-10-01T00:00:00Z", render_error: null, archived_at: null, countries: ["GB"], company: null, focus: null, color_hue: 40 },
];
const PERSONAL = {
  first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", phone: "+44 20 0000 0000", address: "1 Street",
  city: "London", state: "LDN", postal_code: "N1", country: "United Kingdom", linkedin: "x", github: "x", website: "x",
};

function render({ applyIn = ["DE", "UK", "US"], profile = { personal: PERSONAL } } = {}) {
  return renderElement(withRouter(React.createElement(ProfileView, { focus: () => {} })), [
    [["setup-status"], STATUS],
    [["settings", "autofill"], { key: "autofill_profile", value: profile }],
    [["settings", "eeo-consent"], { key: "eeo_consent", value: CONSENT }],
    [["settings", "market"], {
      key: "market", value: { home: "DE", apply_in: applyIn, market: "DE" }, home: "DE", apply_in: applyIn,
      markets: MARKETS, currency: "EUR", offers_eeo: false,
    }],
    [["settings", "job-preferences"], { key: "job_preferences", value: PREFS }],
    [["settings", "persona"], { key: "persona", value: "I design calm tools." }],
    [["base-resumes", { includeArchived: false }], RESUMES],
    [["base-resumes", { includeArchived: true }], RESUMES],
    [["kb", "profile"], { contact: { name: "Ada Lovelace" }, summary: "", skills: [], notes: "", updated_at: "" }],
    [["role-categories"], []],
    [["settings", "money"], { key: "money", value: { home_currency: null, period: "year", hours_per_year: 2080, show_posted: true }, home_currency: "EUR" }],
  ]);
}

test("the header: your name, where you live and apply, and the sections setup status says are ready", () => {
  const html = render();
  assert.match(html, /<h1[^>]*>Ada Lovelace<\/h1>/);
  assert.match(html, /Lives in Germany · applies in Germany, United Kingdom, United States/);
  // personal and job preferences ready; work permits, start and pay, diversity and the persona not.
  assert.match(html, /aria-label="2 of 6 sections ready"/);
  assert.doesNotMatch(html, /About you, and your answers for job forms/);
});

test("next up asks the first country's work permit in place, in that country's words, with no filled button", () => {
  const html = render();
  assert.match(html, /Next up · Work permits · Germany/);
  assert.match(html, /<h2[^>]*>Can you work in this country now\?<\/h2>/);
  assert.match(html, /Never guessed for you/);
  // A Yes or No moves on by itself: nothing on the page is filled.
  assert.equal((html.match(FILLED) ?? []).length, 0);
});

test("a typed answer next up has Next, the view's one filled button", () => {
  const permits = { authorized_now: true, sponsorship_now: false, sponsorship_future: false };
  const html = render({
    applyIn: ["DE"],
    profile: { personal: { ...PERSONAL, phone: "" }, work_auth_by_country: { DE: permits } },
  });
  assert.match(html, /Next up · Contact/);
  assert.match(html, /<label for="[^"]+">Phone<\/label>/);
  assert.equal((html.match(FILLED) ?? []).length, 1);
});

test("nine tiles, each a closed disclosure for its editor under the grid", () => {
  const html = render();
  const tiles = html.match(/<button id="profile-tile-\w+-button"[^>]*aria-expanded="false"/g) ?? [];
  assert.equal(tiles.length, 9);
  assert.equal((html.match(/role="region" aria-label="[^"]+" tabindex="-1" hidden=""/g) ?? []).length, 9);
  assert.doesNotMatch(html, /Save answers/);
});

test("work permits: one set per country you apply in, the visa status only for the United States", () => {
  const html = render();
  const sets = [...html.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>([^<]+)<\/legend>(.*?)<\/fieldset>/g)];
  assert.deepEqual(sets.map((m) => m[1]), ["Germany", "United Kingdom", "United States"]);
  const [de, uk, us] = sets.map((m) => m[2]);
  assert.match(de, /Can you work in this country now\?/);
  assert.match(uk, /Do you have the right to work in the UK now\?/);
  assert.match(us, /Work authorization status/);
  for (const set of [de, uk]) assert.doesNotMatch(set, /Work authorization status/);
  for (const set of [de, uk, us]) assert.match(set, /Authorization expires on/);
  // Each control names its country, so an answer lands on that country's own entry.
  assert.match(uk, /id="af-permit-UK-sponsorship_now"/);
});

test("a country chip carries the square of a base resume made for it", () => {
  const html = render();
  assert.match(html, /United Kingdom<span class="sr-only">, Product designer \(UK\) resume<\/span>/);
  assert.match(html, /bg-resume/);
});

test("diversity is folded beside its consent, and only where a country has a checked set", () => {
  const html = render();
  assert.match(html, /<div id="autofill-eeo">/);
  assert.match(html, /Voluntary · United Kingdom, United States · 0 of 4 answered/);
  assert.match(html, /Let the Companion fill these answers/);
  const germanyOnly = render({ applyIn: ["DE"] });
  assert.match(germanyOnly, /Not asked where you apply/);
  assert.doesNotMatch(germanyOnly, /id="eeo-standing-consent"/);
});
