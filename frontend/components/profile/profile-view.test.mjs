// Profile rendered with seeded reads (design refresh, Task 7.2). pytest runs it:
// backend/tests/test_frontend_profile_tiles.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement, servedQuestions, withRouter } from "../render-harness.mjs";

const { ProfileView } = load("components/profile/profile-view.tsx");

// The one filled button's classes (components/ui/button.tsx, variant "default").
const FILLED = /bg-primary text-primary-foreground/g;

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false },
  { key: "IN", label: "India", country_code: "IN", currency: "INR", date_format: "DMY", offers_eeo: false },
  { key: "AE", label: "United Arab Emirates", country_code: "AE", currency: "AED", date_format: "DMY", offers_eeo: false },
  { key: "NL", label: "Netherlands", country_code: "NL", currency: "EUR", date_format: "DMY", offers_eeo: false },
];
// GET /api/countries, in code order (a few of them).
const COUNTRIES = [
  { code: "AE", name: "United Arab Emirates" }, { code: "DE", name: "Germany" }, { code: "GB", name: "United Kingdom" },
  { code: "IN", name: "India" }, { code: "NL", name: "Netherlands" }, { code: "US", name: "United States" },
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
// Citizenship is a Country answers question; an Indian citizenship settles nothing in Germany, the UK or the US.
const PERSONAL = {
  first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", phone: "+44 20 0000 0000", address: "1 Street",
  city: "London", state: "LDN", postal_code: "N1", country: "United Kingdom", linkedin: "x", github: "x", website: "x",
  citizenships: ["IN"],
};

function render({
  home = "DE",
  applyIn = ["DE", "UK", "US"],
  served = applyIn,
  chosen = true,
  citizenships = [],
  profile = { personal: PERSONAL },
  consent = CONSENT,
} = {}) {
  return renderElement(withRouter(React.createElement(ProfileView, { focus: () => {} })), [
    [["setup-status"], STATUS],
    [["settings", "autofill"], { key: "autofill_profile", value: profile }],
    [["settings", "eeo-consent"], { key: "eeo_consent", value: consent }],
    [["settings", "market"], {
      key: "market", value: { home, apply_in: applyIn, market: home, chosen }, home, apply_in: applyIn,
      markets: MARKETS, currency: "EUR", offers_eeo: false,
    }],
    [["settings", "form-questions"], servedQuestions(home, served, { citizenships, chosen })],
    [["countries"], COUNTRIES],
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
  assert.match(html, /Next up · Country answers · Germany/);
  assert.match(html, /<h2[^>]*>Can you work in this country now\?<\/h2>/);
  assert.match(html, /Never guessed for you/);
  assert.match(html, /Work-permit answers come only from you or your citizenship\. Diversity answers only ever come from you\./);
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

test("contact neither asks nor counts citizenship, which the served set holds (Country answers asks it)", () => {
  const html = render();
  assert.match(html, /id="af-personal-first_name"/);
  assert.doesNotMatch(html, /id="af-personal-citizenships"/);
  const tile = html.match(/<button id="profile-tile-contact-button".*?<\/button>/s)?.[0] ?? "";
  assert.match(tile, />Ready</);
});

test("nine tiles, each a closed disclosure for its editor under the grid", () => {
  const html = render();
  const tiles = html.match(/<button id="profile-tile-\w+-button"[^>]*aria-expanded="false"/g) ?? [];
  assert.equal(tiles.length, 9);
  assert.equal((html.match(/role="region" aria-label="[^"]+" tabindex="-1" hidden=""/g) ?? []).length, 9);
  assert.doesNotMatch(html, /Save answers/);
});

test("next up asks citizenship first, with its country picker, in Country answers", () => {
  const { citizenships: _citizenships, ...personal } = PERSONAL;
  void _citizenships;
  const html = render({ profile: { personal } });
  assert.match(html, /Next up · Country answers</);
  assert.match(html, /<h2[^>]*><label for="[^"]+">Citizen of<\/label><\/h2>/);
  assert.match(html, /aria-label="Citizen of"/);
  // Next is the view's one filled button, as for a typed answer, and waits for a country.
  assert.equal((html.match(FILLED) ?? []).length, 1);
  const lead = html.slice(html.indexOf("Next up · Country answers"));
  assert.match(lead.match(/<button[^>]*>Next<\/button>/)?.[0] ?? "", /aria-disabled="true"/);
});

test("country answers: one set per country you apply in, the visa status only for the United States", () => {
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

test("country answers ask only the countries the served set lists, never one it has no questions for", () => {
  // The market setting already names the United States; the questions read for it have not arrived.
  const html = render({ served: ["DE", "UK"] });
  const sets = [...html.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>([^<]+)<\/legend>/g)];
  assert.deepEqual(sets.map((m) => m[1]), ["Germany", "United Kingdom"]);
  assert.doesNotMatch(html, /United States<\/span><span class="text-muted-foreground">/);
});

test("a country chip carries the square of a base resume made for it", () => {
  const html = render();
  assert.match(html, /United Kingdom<span class="sr-only">, Product designer \(UK\) resume<\/span>/);
  assert.match(html, /bg-resume/);
});

// The Diversity questions fold: its summary, then what it says when opened.
const diversityFold = (html) => {
  const fold = html.slice(html.indexOf('<div id="autofill-eeo">'), html.indexOf('<div id="autofill-eligibility">'));
  const summary = fold.match(/>Diversity questions<\/span><span[^>]*>([^<]*)<\/span>/)?.[1];
  return { fold, summary };
};

test("diversity is folded beside its consent, and only where a country has a checked set", () => {
  const html = render();
  assert.match(html, /<div id="autofill-eeo">/);
  assert.match(html, /Voluntary · United Kingdom, United States · 0 of 4 answered/);
  assert.match(html, /Let the Companion fill these answers/);
  const germanyOnly = render({ applyIn: ["DE"] });
  assert.match(germanyOnly, /Not asked where you apply/);
  assert.doesNotMatch(germanyOnly, /id="eeo-standing-consent"/);
});

test("diversity names the countries the served set lists: the US chosen, the US named", () => {
  const { fold, summary } = diversityFold(render({ applyIn: ["US"] }));
  assert.match(summary, /^Voluntary · United States · 0 of 4 answered/);
  assert.match(fold, /Asked only where a set is checked against official forms: United States\./);
});

test("diversity names none of India, the UAE, Germany and the Netherlands, which have no checked set", () => {
  const html = render({ home: "IN", applyIn: ["IN", "AE", "DE", "NL"], citizenships: ["IN"] });
  const { fold, summary } = diversityFold(html);
  assert.equal(summary, "Not asked where you apply");
  assert.match(fold, /None of the countries you apply in has a checked set of these questions/);
  assert.doesNotMatch(fold, /United States|id="eeo-standing-consent"/);
  // Where you apply says so for the countries picked.
  assert.match(html, /no checked diversity questions for India, United Arab Emirates, Germany, and Netherlands, so/);
});

test("next up's diversity card names the served countries with a checked set", () => {
  const permits = { status: "citizen", authorized_now: true, sponsorship_now: false, sponsorship_future: false };
  const preferences = {
    desired_salary: "x", notice_period: "x", earliest_start_date: "2026-11-01", willing_to_relocate: false, how_heard: "x",
  };
  const html = render({
    applyIn: ["US"],
    profile: { personal: PERSONAL, work_auth_by_country: { US: permits }, preferences },
  });
  assert.match(html, /Next up · Diversity questions/);
  assert.match(html, /Asked where a set is checked against official forms: United States\. Answer them or decline/);
});

test("while the Companion may not use the diversity answers, the fold says it won't fill them", () => {
  // Answered, and declined: setup readiness counts them either way (the answers are given), so the summary
  // says what the consent switch decides.
  const declined = { veteran_status: "decline", disability_status: "decline", gender: "decline", hispanic_latino: "decline" };
  const off = render({ profile: { personal: PERSONAL, eeo: declined } });
  assert.match(off, /Voluntary · United Kingdom, United States · set to decline · the Companion won&#x27;t fill these until you let it/);
  const on = render({
    profile: { personal: PERSONAL, eeo: declined },
    consent: { ...CONSENT, enabled: true, acknowledged_at: "2026-10-01T00:00:00Z" },
  });
  assert.match(on, /Voluntary · United Kingdom, United States · set to decline/);
  assert.doesNotMatch(on, /won&#x27;t fill these/);
});

// An Indian citizen who lives in India and applies in India, the UAE, Germany and the Netherlands: the server
// settles India's three permit answers from the citizenship, and asks CEFR levels for Germany and the Netherlands.
const INDIA = ["IN", "AE", "DE", "NL"];
const ASHA = {
  personal: { ...PERSONAL, first_name: "Asha", last_name: "Rao", country: "India", citizenships: ["IN"] },
  languages: [{ language: "German", speak: "Fluent", cefr: "B2" }, { language: "Hindi", native: true }],
};
const renderIndia = (profile = ASHA) =>
  render({ home: "IN", applyIn: INDIA, citizenships: ["IN"], profile });
const tileButton = (html, id) => html.match(new RegExp(`<button id="profile-tile-${id}-button".*?</button>`, "s"))?.[0] ?? "";

test("the tile is Country answers: citizenship first, then one line per country you apply in", () => {
  const html = renderIndia();
  const tile = tileButton(html, "permits");
  assert.match(tile, />Country answers</);
  const lines = [...tile.matchAll(/<span class="min-w-0 flex-1 truncate">([^<]+)<\/span><span class="min-w-0 truncate text-muted-foreground">([^<]+)</g)];
  assert.deepEqual(lines.map((m) => [m[1], m[2]]), [
    ["Citizen of", "India"],
    ["India", "can work now"],
    ["United Arab Emirates", "not answered"],
    ["Germany", "not answered"],
    ["Netherlands", "not answered"],
  ]);
  assert.match(tile, /Needs you/);
  assert.match(html, /role="region" aria-label="Country answers"/);
});

test("country answers: Citizen of at the top, then each country's permits and its own answers", () => {
  const html = renderIndia();
  const region = html.match(/aria-label="Country answers" tabindex="-1" hidden="" class="outline-none">(.*?)<\/div><div id="profile-tile-jobs"/s)?.[1];
  assert.ok(region, "the Country answers editor renders under the grid");
  const citizen = region.indexOf(">Citizen of</label>");
  assert.ok(citizen > 0, "Citizen of is asked");
  assert.ok(citizen < region.indexOf("<fieldset"), "before the first country");
  // The picker shows the stored code by its name.
  assert.match(region, /India<button[^>]*aria-label="Remove India"/);
  const sets = [...region.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>([^<]+)<\/legend>(.*?)<\/fieldset>/g)];
  assert.deepEqual(sets.map((m) => m[1]), ["India", "United Arab Emirates", "Germany", "Netherlands"]);
  const [india, uae, germany, netherlands] = sets.map((m) => m[2]);
  // India's own pay, after its permits; the UAE's status list and its own questions.
  assert.ok(india.indexOf("Expected CTC") > india.indexOf("Will you need visa sponsorship later?"));
  assert.match(india, /id="af-answer-IN-current_ctc"/);
  assert.match(uae, /Immigration status/);
  assert.match(uae, /Are you in the UAE now\?/);
  assert.match(netherlands, /excluding holiday allowance/);
  assert.match(germany, /id="af-permit-DE-authorized_now"/);
});

test("India's three permit answers come from the citizenship, each with a way to answer differently", () => {
  const html = renderIndia();
  const sets = [...html.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>([^<]+)<\/legend>(.*?)<\/fieldset>/g)];
  const [india, ...others] = sets.map((m) => m[2]);
  assert.equal((india.match(/From your citizenship \(India\)/g) ?? []).length, 3);
  assert.equal((india.match(/>Answer differently</g) ?? []).length, 3);
  for (const key of ["authorized_now", "sponsorship_now", "sponsorship_future"]) {
    assert.doesNotMatch(india, new RegExp(`id="af-permit-IN-${key}"`), `${key} shows as words, not a control`);
    // Each row is a group named by its question, so Answer differently is read with it.
    assert.match(india, new RegExp(`role="group" aria-labelledby="af-permit-IN-${key}-label"`));
  }
  assert.match(india, /<span id="af-permit-IN-authorized_now-label"[^>]*>Can you work in this country now\?<\/span><p class="text-body-medium">Yes<\/p>/);
  // A right to work from citizenship does not run out: India asks no expiry; the UAE, settled by nothing, does.
  assert.doesNotMatch(india, /Authorization expires on/);
  assert.match(others[0], /id="af-permit-AE-authorization_expires_on"/);
  for (const set of others) assert.doesNotMatch(set, /From your citizenship/);
  assert.doesNotMatch(india, /Your answer differs/);
});

test("an answer that differs from what the citizenship settles: the rest are asked, and a note says why", () => {
  // Saved, the server has not been asked again yet: it still serves India as settled.
  const html = renderIndia({ ...ASHA, work_auth_by_country: { IN: { authorized_now: false } } });
  const [india] = [...html.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>India<\/legend>(.*?)<\/fieldset>/g)].map((m) => m[1]);
  assert.match(india, /Your answer differs from what your citizenship settles, so these are asked\./);
  assert.doesNotMatch(india, /From your citizenship \(India\)/);
  for (const key of ["authorized_now", "sponsorship_now", "sponsorship_future", "authorization_expires_on"]) {
    assert.match(india, new RegExp(`id="af-permit-IN-${key}"`), key);
  }
  assert.match(html, /Next up · Country answers · India/);
});

test("a citizenship stored as a plain string shows in the picker, and Next stores it as a list", () => {
  const { citizenships: _citizenships, ...personal } = PERSONAL;
  void _citizenships;
  const html = render({ profile: { personal: { ...personal, citizenships: "India" } } });
  assert.match(html, /Next up · Country answers</);
  const lead = html.slice(html.indexOf("Next up · Country answers"));
  assert.match(lead, /India<button[^>]*aria-label="Remove India"/);
  // Next is not held back: it writes the list, and the server turns the name into a code.
  const next = lead.match(/<button[^>]*>Next<\/button>/)?.[0] ?? "";
  assert.match(next, /aria-disabled="false"/);
});

test("an answer you gave the same way shows as yours, not as from your citizenship", () => {
  const html = renderIndia({ ...ASHA, work_auth_by_country: { IN: { authorized_now: true } } });
  const [india] = [...html.matchAll(/<fieldset class="space-y-4"><legend[^>]*>.*?<\/svg>India<\/legend>(.*?)<\/fieldset>/g)].map((m) => m[1]);
  assert.match(india, /id="af-permit-IN-authorized_now"/);
  assert.equal((india.match(/From your citizenship \(India\)/g) ?? []).length, 2);
});

test("next up skips what the citizenship settled and asks the UAE next", () => {
  const html = renderIndia();
  assert.match(html, /Next up · Country answers · United Arab Emirates/);
  assert.match(html, /<h2[^>]*>Can you work in the UAE without an employer sponsoring your residence visa\?<\/h2>/);
});

test("the screening questions fold, and a CEFR level on each language", () => {
  const html = renderIndia();
  assert.match(html, /<div id="autofill-eligibility">/);
  assert.match(html, />Screening questions</);
  assert.match(html, /Past employers, and what your countries&#x27; forms ask/);
  assert.doesNotMatch(html, />Eligibility</);
  assert.match(tileButton(html, "languages"), /German · Fluent · B2/);
  for (const i of [0, 1]) assert.match(html, new RegExp(`<label[^>]*for="af-languages-${i}-cefr"[^>]*>Level \\(CEFR\\)</label>`));
  // The UK alone asks no CEFR level.
  assert.doesNotMatch(render({ applyIn: ["UK"], profile: ASHA }), /af-languages-\d-cefr/);
});

test("with no country chosen: nothing picked, no country's questions, and a way to choose", () => {
  const html = render({ home: "US", applyIn: ["US"], served: [], chosen: false });
  assert.match(html, /Where you live and apply: not chosen yet/);
  assert.match(tileButton(html, "where"), /No country chosen yet/);
  // The stored default, the US, is not shown as picked.
  const applyIn = html.match(/<div role="group" aria-labelledby="[^"]+" aria-describedby="[^"]+" class="flex flex-wrap gap-2">(.*?)<\/div>/s)?.[1] ?? "";
  assert.match(applyIn, /United States/);
  assert.doesNotMatch(applyIn, /aria-pressed="true"/);
  // Country answers: Citizen of, then a way to Where you apply, and no country's set.
  assert.match(html, />Citizen of<\/label>/);
  assert.match(html, /No country chosen yet\. Choose where you apply/);
  assert.match(html, />Where you apply<\/button>/);
  assert.doesNotMatch(html, /<fieldset class="space-y-4">/);
  // Said on one tile only: Where you apply.
  assert.doesNotMatch(tileButton(html, "permits"), /No country chosen yet/);
  // Diversity names no country (the stored US is a default, never a choice), and its summary says why.
  const { fold, summary } = diversityFold(html);
  assert.equal(summary, "No country chosen yet");
  assert.match(fold, /No country chosen yet\. These are asked only where a country you apply in has a checked set\./);
  assert.doesNotMatch(fold, /United States|Voluntary ·|id="eeo-standing-consent"/);
  // Next up asks no diversity question, and the note under Where you apply names no country without a set.
  assert.doesNotMatch(html, /Next up · Diversity questions/);
  assert.doesNotMatch(html, /no checked diversity questions for/);
  // Next up asks where you apply first: until then every form pauses on the permits no country asks.
  assert.match(html, /Next up · Where you apply/);
  assert.match(html, /The countries you apply in/);
  assert.match(html, /<button[^>]*bg-primary text-primary-foreground[^>]*>Choose countries<\/button>/);
  assert.ok(html.indexOf("Next up · Where you apply") < html.indexOf(">Citizen of</label>"));
});
