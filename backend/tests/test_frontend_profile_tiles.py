"""Pins for Profile as tiles: facts about you, saving as you go (design refresh plan, Task 7.2; D9, D10, D11).

- **Nothing removed.** Every Profile item still has a home in `components/profile/*` or the page
  (`PROFILE_ITEMS`, the plan's list of the screen's words; the diversity consent's label is the real one,
  "Let the Companion fill these answers"). All 62 items of the "Where everything lives" board's Profile
  group, by their board labels and in the tile or fold that holds each, are
  `test_frontend_every_item_has_a_home.py`'s.
- **Country answers per country.** Citizenship first, then one set per apply-in country as the served
  question set lists them (`GET /api/settings/autofill/questions` `countries`), worded by that market's
  `work_auth_vocab` (data): the keys `authorized_now`, `sponsorship_now` and `sponsorship_future`
  everywhere, the visa status only where the vocabulary is `us_visa`, then the country's own answers. A
  permit answer a citizenship settles shows as "From your citizenship", never as a control.
- **Saves as you go.** The Autofill tab's Save button is gone; the answers autosave (`useAutosave`) and
  report with `AutosaveStatus`.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services import form_questions
from app.services.markets import keys as market_keys
from tests.node_ts import run_node_render_test, run_node_test

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _src(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _between(src: str, start: str, end: str) -> str:
    at = src.index(start)
    return src[at : src.index(end, at + len(start))]


PROFILE_ITEMS = [
    "First name", "Last name", "Email", "Phone", "Street address", "Address line 2", "City", "State",
    "Postal code", "Country", "LinkedIn profile link", "GitHub link", "Website", "Fill from career history",
    "You live in", "You apply in", "Work authorization status", "Authorization expires on",
    "Roles you want", "Years of experience", "Work location", "Locations", "Minimum salary", "Job types",
    "Persona", "Draft from my career history", "Desired salary", "Notice period", "Earliest start date",
    "Willing to relocate?", "How did you hear about the job?", "School", "Degree", "Major", "GPA",
    "Start year", "Graduation year", "Add education", "Language", "Add language", "Add question",
    "Let the Companion fill these answers", "Are you a veteran?", "Disability status", "Gender",
    "How you describe your gender", "Hispanic or Latino?", "Race or ethnicity", "Decline the rest",
    "Are you 18 or older?", "Have you worked for the company you're applying to?",
    "Subject to a restrictive covenant?",
]


def _profile_source() -> str:
    src = "".join(p.read_text(encoding="utf-8") for p in sorted((_FRONTEND / "components/profile").glob("*.tsx")))
    # The questions the tiles render (labels, options) are the catalog the backend serves them, shared with
    # Setup; education and languages are in one importable module.
    src += (_ROOT / "backend/app/services/data/form_questions.yaml").read_text(encoding="utf-8")
    src += _src("lib/autofill-options.ts")
    return src + _src("app/profile/page.tsx")


def test_every_profile_item_still_has_a_home():
    src = _profile_source()
    missing = [label for label in PROFILE_ITEMS if label not in src]
    assert not missing, missing


def test_the_tiles_and_folds_are_the_boards():
    """Nine tiles in the board's order, then two folds: Diversity and Screening questions. Work permits became
    Country answers and Eligibility Screening questions; their ids stay, so links still land."""
    lib = _src("lib/profile-tiles.ts")
    tiles = _between(lib, "export const PROFILE_TILES = [", "] as const")
    assert re.findall(r'title: "([^"]+)"', tiles) == [
        "Contact", "Where you apply", "Country answers", "Jobs you want", "How you come across", "Start and pay",
        "Education", "Languages", "Your own questions",
    ]
    assert '{ id: "permits", title: "Country answers", anchors: ["autofill-work_auth"]' in tiles
    folds = _between(lib, "export const PROFILE_FOLDS = [", "] as const")
    assert re.findall(r'title: "([^"]+)"', folds) == ["Diversity questions", "Screening questions"]
    assert '{ id: "eligibility", title: "Screening questions", anchors: ["autofill-eligibility"]' in folds


# ------------------------------------------------------------------ Country answers, per country

def test_the_work_permit_questions_node_suite_runs():
    """Each vocabulary's questions, keys and country words (lib/autofill-options.test.ts)."""
    result = run_node_test("lib/autofill-options.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_each_country_counts_the_three_keys_and_only_the_us_counts_the_status():
    """The status question is built per market from its list: required in the US only, so no other
    country's count moves (Decision 6 of docs/plans/2026-10-30-country-form-questions.md)."""
    expected = ["authorized_now", "sponsorship_now", "sponsorship_future"]
    for country in form_questions.resolve(home="US", apply_in=market_keys(), chosen=True, profile=None).countries:
        keys = form_questions.required_keys(country.permits)
        assert keys == (["status", *expected] if country.market == "US" else expected), (country.market, keys)


def test_the_country_answers_tile_asks_one_set_per_country_in_its_own_words():
    """The words come from the served set (data, per market), never decided here."""
    tile = _src("components/profile/work-permits.tsx")
    # One set per country the served set lists (in apply-in order), never a newer market list's country.
    assert "questionSet.countries.map((country) => ( <CountrySet key={country.market} country={country}" in _flat(tile)
    assert "const fields = shownPermitFields(profile, questionSet, market, answering);" in tile
    # Each country's answers are its own entry, keyed by market ("UK", not "GB"): its permits, then its own.
    assert "withPermit(current, questionSet, market, key, next)" in tile
    assert "withCountryAnswer(current, country, key, next)" in tile
    assert "fields={country.answers}" in tile
    # The frontend never words a question from a market's vocabulary: the market list carries none for it.
    option = _between(_src("lib/types.ts"), "export interface MarketOption {", "\n}")
    assert "work_auth_vocab" not in option


def test_the_home_set_asks_its_pay_as_the_desired_salary():
    """Where you live (the served set's `home`), the country's pay is `preferences.desired_salary`, read and written
    there, the one place the server keeps it. A country is done once its permits and its own required answers are,
    and counted as one set; Setup's permit step reads the permits alone (Decision 8 of
    docs/plans/2026-11-02-start-and-pay.md). The behaviour is profile-view.test.mjs's; these pin who does it."""
    tile = _src("components/profile/work-permits.tsx")
    for symbol in ("countryAnswerEntry(profile, country)", "countryDone(", "countrySetCount(", "openAnswersWords("):
        assert symbol in tile, symbol
    options = _src("lib/autofill-options.ts")
    for symbol in ("export function countryAnswerEntry(", "export function withCountryAnswer(", "HOME_PAY"):
        assert symbol in options, symbol


def test_country_answers_asks_citizenship_first_and_shows_what_it_settles():
    """Citizen of is the one new required answer (Decision 6): asked here with the country picker, never in
    Contact, counted on this tile as setup readiness counts it in `work_auth`. A permit answer it settles is
    the server's `derived`, shown only where nothing is given, and Answer differently brings the control back.
    Saving it reads the questions again, so what it settles is the server's, never a guess here."""
    tile = _src("components/profile/work-permits.tsx")
    assert tile.index('<Label htmlFor="af-citizenships"') < tile.index("<CountrySet key={country.market}")
    assert "onChange={(codes) => update(SURFACE, (current) => withCitizenships(current, codes))}" in tile
    # One picker for Profile, Next up and Setup.
    picker = _src("components/profile/citizenship-picker.tsx")
    assert "names={CITIZEN_NAMES}" in picker and 'GB: "United Kingdom (British citizen)"' in picker
    for rel in ("components/profile/work-permits.tsx", "components/profile/next-up.tsx"):
        assert 'from "@/components/profile/citizenship-picker";' in _src(rel), rel
    assert "const open = !citizenDone || rows.some((row) => !row.done);" in tile
    # Words only where nothing is given and you are not answering it yourself; a control in use stays one.
    assert "if (!by || answered(field, entry[field.key])) continue;" in tile
    assert "hints[field.key] = `Left unset, your citizenship answers ${answerWords(field, by.value)}.`;" in tile
    assert "answerYourself(key);" in tile
    assert "From your citizenship ({nameOf(by.via)})" in tile and "Answer differently" in tile
    # A right to work from citizenship does not run out: the expiry is not asked while it settles the country.
    options = _src("lib/autofill-options.ts")
    assert "!(citizen && field.key === PERMIT_EXPIRY && isBlank(stored[field.key]))" in options
    # What the server settled, only ever narrowed here: by your citizenships now, and by an answer that differs.
    narrowed = _between(options, "export function derivedPermits(", "\n}\n")
    assert "stillCitizen(profile, countryQuestions(questionSet, market)?.derived ?? {})" in narrowed
    provider = _flat(_src("components/profile/autofill-profile.tsx"))
    assert (
        "if (settles(before) !== settles(result.value)) { await qc.invalidateQueries({ queryKey: "
        "formQuestionsQuery.queryKey }); }"
    ) in provider
    assert 'if (citizenship && !citizenship.optional && !citizenshipAnswered(profile, questionSet, codes)) {' in options
    # A citizenship held by name (a hand edit) is unanswered once the country list is read, as it settles nothing.
    assert "&& !citizenshipIsLoose(profile, codes));" in options
    assert 'out.push({ kind: "citizenship", field: citizenship });' in options
    # One rule for what is still open, for the count, Next up and Setup's done card.
    assert "for (const field of openPermitFields(profile, questionSet, market)) out.push(" in options
    assert "const [open] = openPermitFields(editing, questionSet, country.market);" in _src("components/setup/setup-done.tsx")


def test_the_market_list_carries_each_markets_work_permit_vocabulary():
    router = (_ROOT / "backend/app/routers/settings.py").read_text(encoding="utf-8")
    markets = _between(router, '"markets": [', "for k in markets.keys()")
    assert '"work_auth_vocab": markets.get(k)["work_auth_vocab"],' in markets


def test_contact_counts_and_names_the_state_line_by_where_you_live():
    """Data again (markets.yaml `asks_state`, `state_label`): the server resolves the state line for the home
    market, and Contact's count, its editor and Next up read that served set, so a Dutch home is done without a
    state and a Canadian one is asked its province."""
    router = (_ROOT / "backend/app/routers/settings.py").read_text(encoding="utf-8")
    markets = _between(router, '"markets": [', "for k in markets.keys()")
    assert '"asks_state": markets.get(k)["asks_state"],' in markets
    assert '"state_label": markets.get(k)["state_label"],' in markets
    # The served set carries the state line resolved; the frontend reads no market's address rule itself.
    option = _between(_src("lib/types.ts"), "export interface MarketOption {", "\n}")
    assert "asks_state" not in option and "state_label" not in option
    def state(home: str):
        personal = next(g for g in form_questions.resolve(home=home, apply_in=[home], chosen=True, profile=None).groups if g.key == "personal")
        return next(f for f in personal.fields if f.key == "state")

    assert (state("NL").label, state("NL").optional) == ("Province", True)
    assert (state("CA").label, state("CA").optional) == ("Province", False)
    contact = _src("components/profile/contact.tsx")
    assert 'const count = groupCount(profile, questionSet, "personal");' in contact
    assert "fields={contactFields(questionSet)}" in contact
    options = _src("lib/autofill-options.ts")
    # Contact's count, its editor and Next up read the personal group less citizenship (Country answers').
    assert 'const fields = group === "personal" ? contactFields(questionSet) : groupFields(questionSet, group);' in options
    assert 'return groupFields(questionSet, "personal").filter((field) => field.type !== "countries");' in options
    nxt = _src("components/profile/next-up.tsx")
    assert ": groupCount(profile, questionSet, current.group);" in nxt


# ---------------------------------------------------------------------------- Saving

def test_the_answers_save_as_you_go():
    src = _profile_source()
    assert "Save answers" not in src and "saveOnce(" not in _src("components/profile/autofill-profile.tsx")
    provider = _src("components/profile/autofill-profile.tsx")
    assert "useAutosave<Profile>(" in provider


def test_each_editor_says_saved_only_once_its_own_edit_has_saved():
    """Several editors change one profile saved whole. Each editor's status follows its OWN newest edit
    (`lib/save-surfaces.ts`): Saving until a write that carries it lands, Not saved when the last write
    carrying it failed, nothing for an editor with no edit. Following only the last editor said Saved on
    Next up while the write carrying its phone was still in flight, and showed a failure on one editor."""
    result = run_node_test("lib/save-surfaces.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr
    provider = _flat(_src("components/profile/autofill-profile.tsx"))
    assert "last === surface" not in provider
    assert "...surfaceStatus(saves, surface, answers)" in provider
    # Each write records the edits it carries when it goes out, and marks them saved only once it lands.
    assert "const through = savesNow.current.seq;" in provider
    assert "track((state) => landed(state, through));" in provider
    assert "track((state) => edited(state, surface)); answers.update(next);" in provider


def test_an_open_page_reads_the_answers_again_when_you_come_back():
    """The Companion's pause row learns answers into the profile from another window, and Profile and Setup save
    the WHOLE profile: one that kept its old copy would erase a learned answer on its next edit. So each reads it
    again on focus (`"always"`, since a learn within the 30 s a read stays fresh would be skipped by `true`) and
    takes the new copy only while every edit is on the server (`adopt`)."""
    assert 'refetchOnWindowFocus: "always",' in _src("components/profile/use-autofill-query.ts")
    for rel in ("components/profile/profile-view.tsx", "components/setup/setup-flow.tsx"):
        assert "useAutofillQuery()" in _src(rel), rel
    # No second query on the key that could miss the rule.
    others = [
        str(path.relative_to(_FRONTEND))
        for tree in ("app", "components", "lib", "hooks")
        for path in sorted((_FRONTEND / tree).rglob("*.ts*"))
        if path.name != "use-autofill-query.ts" and 'queryKey: ["settings", "autofill"]' in path.read_text(encoding="utf-8")
    ]
    assert others == [], others
    provider = _src("components/profile/autofill-profile.tsx")
    adopt = _between(provider, "export function useAdoptServed(", "\n}\n")
    assert "if (served === seen.current) return;" in adopt
    # A copy declined while a save was on its way (that save's own result, citizenships as codes) is offered
    # again once nothing is: `seen` moves only when adopt takes it.
    assert "if (adopt(profileForEditing(served))) seen.current = served;" in adopt
    assert "}, [served, adopt, pending]);" in adopt
    assert "return false;" in _between(_src("lib/use-autosave.ts"), "const adopt = useCallback(", "}, []);")
    # Profile's provider and Setup's Form answers both take a newer copy through it, and save the same way.
    assert "useAdoptServed(served, answers.adopt, answers.pending);" in provider
    setup = _between(_src("components/setup/setup-answers-step.tsx"), "export function useSetupAnswers(", "\n}\n")
    assert "useAdoptServed(served, answers.adopt, answers.pending);" in setup and "const save = useSaveAnswers();" in setup
    assert "const answers = useSetupAnswers(data.profile);" in _src("components/setup/setup-flow.tsx")
    # Last, because it skips where the web app's packages are not installed (the backend CI job).
    result = run_node_render_test("components/profile/use-autofill-query.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_profile_editor_stays_mounted_and_saves_as_you_go():
    """One open tile at a time, each editor kept mounted while closed (typed drafts and leave guards survive).
    Every Profile editor saves as you go, the persona too (owner, 2026-10-22)."""
    view = _src("components/profile/profile-view.tsx")
    assert "hidden={sections.tile !== tile.id}" in view
    assert "{tiles[tile.id].panel}" in view
    for path in (_FRONTEND / "components/profile").glob("*.tsx"):
        assert "saveOnce(" not in path.read_text(encoding="utf-8"), path.name


def test_only_a_drafted_persona_waits_for_a_click():
    """A drafted persona is read before it is kept (inv-drafted-answers): it waits for Use this draft or Discard,
    and the status says nothing then."""
    persona = _src("components/profile/how-you-come-across.tsx")
    assert "useAutosave(initial, (next) => save.mutateAsync(next))" in persona
    assert "<AutosaveStatus pending={pending} failed={failed} idle={review === null} onRetry={retry} />" in persona
    # The draft lands in `review`, never in the autosaved value; only Use this draft hands it over.
    landed = persona[persona.index("const draft = useMutation(") : persona.index("// One request per gesture")]
    assert "setReview(result.draft);" in landed and "update(" not in landed
    assert "Use this draft" in persona and "Discard" in persona


# ------------------------------------------------------------------------- Header and Next up

def test_the_header_counts_only_what_setup_status_says():
    header = _src("components/profile/profile-header.tsx")
    ready = _between(header, "export function readySections(", "\n}\n")
    assert "status.autofill.groups" in ready and "status.job_preferences.done" in ready
    assert "status.persona.done" in ready
    # The old descriptive subtitle is gone (D1); the line under the name is your own facts.
    assert "About you, and your answers for job forms." not in _profile_source()
    assert "const facts = `Lives in ${label(market.home)} · applies in ${market.apply_in.map(label).join(\", \")}`;" in header


def test_next_up_asks_the_first_missing_answer_in_place_and_never_guesses():
    nxt = _src("components/profile/next-up.tsx")
    assert "const missing = missingAnswers(profile, questionSet, codes);" in nxt
    assert "Never guessed for you" in nxt
    # A work permit can come from your citizenship (derived when read, never stored): still never a guess.
    assert "Work-permit answers come only from you or your citizenship. Diversity answers only ever come from you." in nxt
    assert "Work-permit and diversity answers only ever come from you." not in nxt
    # Diversity is answered in its fold, beside its consent (D10): Next up only opens it.
    assert 'if (current.kind === "diversity") {' in nxt and "onClick: onOpenDiversity" in nxt
    assert "update(SURFACE, (profileNow) =>" in nxt


def test_next_up_asks_the_home_pay_after_its_permits_and_counts_older_answers():
    """After each country's open permits, its own required answers (the home's pay, which Setup never asks), read
    and written where its list keeps it, through the Country answers helpers. An older answer under a field's
    `legacy` key (notice in words) counts wherever the readers count, as setup readiness counts it."""
    missing = _between(_src("lib/autofill-options.ts"), "export function missingAnswers(", "\n}\n")
    assert 'kind: "own"' in missing and "countryAnswersOpen(" in missing and "answeredIn(" in missing
    nxt = _src("components/profile/next-up.tsx")
    assert "missingValue(" in nxt and "withMissingAnswer(" in nxt
    assert "answeredIn(" in _src("components/profile/start-and-pay.tsx")


def test_next_up_opens_where_you_apply_first_while_no_country_is_chosen():
    """Unchosen, no country's permits are asked, so every form pauses on them: Next up asks where you apply first,
    answered in its tile, which it only opens."""
    nxt = _src("components/profile/next-up.tsx")
    assert 'if (current.kind === "where") {' in nxt
    assert "onClick: onChooseCountries" in nxt
    assert 'onChooseCountries={() => focus("market")}' in _src("components/profile/profile-view.tsx")
    missing = _between(_src("lib/autofill-options.ts"), "export function missingAnswers(", "\n}\n")
    assert 'const out: MissingAnswer[] = questionSet.chosen ? [] : [{ kind: "where" }];' in missing


# ------------------------------------------------------------------------------- The folds

def test_diversity_sits_with_its_consent_and_only_where_a_set_is_checked():
    fold = _src("components/profile/diversity.tsx")
    # The countries come from the served set, never the market setting's `apply_in`, which still stores the
    # US while no country is chosen: none while the set offers no diversity questions.
    helper = _between(_src("lib/autofill-options.ts"), "export function diversityCountries(", "\n}\n")
    assert "if (!questionSet.offers_eeo) return [];" in helper
    assert "questionSet.countries.flatMap((country) =>" in helper
    assert "markets.find((m) => m.key === country.market)?.offers_eeo ? [country.label] : []" in helper
    nxt = _src("components/profile/next-up.tsx")
    for src in (fold, nxt):
        assert "diversityCountries(questionSet, market.markets ?? [])" in src
        assert "market.apply_in" not in src
    assert '<div id="autofill-eeo">' in fold and '<Fold title="Diversity questions"' in fold
    consent = _src("components/profile/diversity-consent.tsx")
    switch = _between(consent, "export function DiversityConsentSwitch(", "\n}\n")
    # The consent date beside the switch, the server-owned stamp (`acknowledged_at` sent empty on a yes).
    assert "{consent.enabled ? <AgreedOn consent={consent} /> : null}" in switch
    assert "acknowledged_at: enabled ? null : consent.acknowledged_at," in consent
    eligibility = _src("components/profile/eligibility.tsx")
    assert '<div id="autofill-eligibility">' in eligibility and 'title="Screening questions"' in eligibility
    assert "Past employers, and what your countries' forms ask" in eligibility


def test_a_country_chip_shows_the_square_of_a_resume_made_for_it():
    where = _src("components/profile/where-you-apply.tsx")
    assert "return code ? resumes.filter((resume) => resume.countries.includes(code)) : [];" in where
    assert "<ResumeSwatch key={resume.slug} hue={resume.color_hue} />" in where
    # The square is identity: the resume's name is read with it.
    assert '<span className="sr-only">' in where
    # D9's words for the two settings, in the fields Profile shares with Setup.
    fields = _src("components/profile/country-fields.tsx")
    assert ">You live in</Label>" in fields and "You apply in\n" in fields
    assert "<LiveInField" in where and "<ApplyInField" in where


def test_old_profile_links_open_their_tile_or_fold():
    result = run_node_test("lib/profile-tiles.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr
    hook = _src("components/profile/use-profile-sections.ts")
    assert "const at = sectionForAnchor(anchor);" in hook


def test_the_contact_fill_node_suite_runs():
    result = run_node_test("lib/contact-from-history.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_profile_view_node_suite():
    """Profile rendered with seeded reads: the header, Next up, the tiles, Country answers per country (an Indian
    citizen in India, the UAE, Germany and the Netherlands too), the folds, and no country chosen."""
    result = run_node_render_test("components/profile/profile-view.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr
