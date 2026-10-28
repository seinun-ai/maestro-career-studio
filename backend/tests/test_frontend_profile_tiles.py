"""Pins for Profile as tiles: facts about you, saving as you go (design refresh plan, Task 7.2; D9, D10, D11).

- **Nothing removed.** Every Profile item still has a home in `components/profile/*` or the page
  (`PROFILE_ITEMS`, the plan's list of the screen's words; the diversity consent's label is the real one,
  "Let the Companion fill these answers"). All 62 items of the "Where everything lives" board's Profile
  group, by their board labels and in the tile or fold that holds each, are
  `test_frontend_every_item_has_a_home.py`'s.
- **Work permits per country.** One set per apply-in country, worded by that market's `work_auth_vocab`
  (from data, `GET /api/settings/market`): the keys `authorized_now`, `sponsorship_now` and
  `sponsorship_future` everywhere, the visa status only where the vocabulary is `us_visa`.
- **Saves as you go.** The Autofill tab's Save button is gone; the answers autosave (`useAutosave`) and
  report with `AutosaveStatus`.
"""

from __future__ import annotations

import re
from pathlib import Path

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
    # The field definitions the tiles render (labels, options) live in one importable module, shared with Setup.
    src += _src("lib/autofill-options.ts")
    return src + _src("app/profile/page.tsx")


def test_every_profile_item_still_has_a_home():
    src = _profile_source()
    missing = [label for label in PROFILE_ITEMS if label not in src]
    assert not missing, missing


def test_the_tiles_and_folds_are_the_boards():
    """Nine tiles in the board's order, then two folds: Diversity and Eligibility."""
    lib = _src("lib/profile-tiles.ts")
    tiles = _between(lib, "export const PROFILE_TILES = [", "] as const")
    assert re.findall(r'title: "([^"]+)"', tiles) == [
        "Contact", "Where you apply", "Work permits", "Jobs you want", "How you come across", "Start and pay",
        "Education", "Languages", "Your own questions",
    ]
    folds = _between(lib, "export const PROFILE_FOLDS = [", "] as const")
    assert re.findall(r'title: "([^"]+)"', folds) == ["Diversity questions", "Eligibility"]


# ------------------------------------------------------------------ Work permits, per country

def test_the_work_permit_questions_node_suite_runs():
    """Each vocabulary's questions, keys and country words (lib/autofill-options.test.ts)."""
    result = run_node_test("lib/autofill-options.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_each_vocabulary_asks_the_three_keys_and_only_us_visa_asks_the_status():
    lib = _src("lib/autofill-options.ts")
    table = _between(lib, "const WORK_PERMIT_QUESTIONS: Record<WorkAuthVocab, PermitQuestion[]> = {", "\n};")
    for vocab in ("us_visa", "uk", "generic"):
        block = _between(table, f"  {vocab}: [", "\n  ],")
        keys = re.findall(r'key: "(\w+)"', block)
        expected = ["authorized_now", "sponsorship_now", "sponsorship_future"]
        assert keys == (["status", *expected] if vocab == "us_visa" else expected), (vocab, keys)


def test_the_work_permits_tile_asks_one_set_per_country_in_its_own_words():
    """The vocabulary comes from the market list (data), never decided here."""
    tile = _src("components/profile/work-permits.tsx")
    assert "applyIn.map((key) => {" in tile
    assert "workPermitFields(market?.work_auth_vocab)" in tile
    # Each country's answers are its own entry, keyed by market ("UK", not "GB").
    assert "withPermit(current, key, fieldKey, next)" in tile
    types = _src("lib/types.ts")
    option = _between(types, "export interface MarketOption {", "\n}")
    assert "work_auth_vocab: string;" in option


def test_the_market_list_carries_each_markets_work_permit_vocabulary():
    router = (_ROOT / "backend/app/routers/settings.py").read_text(encoding="utf-8")
    markets = _between(router, '"markets": [', "for k in markets.keys()")
    assert '"work_auth_vocab": markets.get(k)["work_auth_vocab"],' in markets


def test_contact_counts_and_names_the_state_line_by_where_you_live():
    """Data again (markets.yaml `asks_state`, `state_label`): Contact's count, its editor and Next up read the
    home market, so a Dutch home is done without a state and a Canadian one is asked its province."""
    router = (_ROOT / "backend/app/routers/settings.py").read_text(encoding="utf-8")
    markets = _between(router, '"markets": [', "for k in markets.keys()")
    assert '"asks_state": markets.get(k)["asks_state"],' in markets
    assert '"state_label": markets.get(k)["state_label"],' in markets
    option = _between(_src("lib/types.ts"), "export interface MarketOption {", "\n}")
    assert "asks_state: boolean;" in option and "state_label: string;" in option
    contact = _src("components/profile/contact.tsx")
    assert 'const count = groupCount(profile, "personal", home);' in contact
    assert 'fields={groupFields("personal", home)}' in contact
    assert contact.count("const home = homeMarket(useMarketQuery().data);") == 2
    nxt = _src("components/profile/next-up.tsx")
    assert ": groupCount(profile, current.group, homeMarket(market));" in nxt


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
    assert "if (served === seen.current) return;" in adopt and "adopt(profileForEditing(served));" in adopt
    # Profile's provider and Setup's Form answers both take a newer copy through it, and save the same way.
    assert "useAdoptServed(served, answers.adopt);" in provider
    setup = _src("components/setup/setup-answers-step.tsx")
    assert "useAdoptServed(profile, answers.adopt);" in setup and "const save = useSaveAnswers();" in setup
    # Last, because it skips where the web app's packages are not installed (the backend CI job).
    result = run_node_render_test("components/profile/use-autofill-query.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_profile_editor_stays_mounted_and_the_persona_keeps_its_save():
    """One open tile at a time, each editor kept mounted while closed (typed drafts and leave guards survive).
    The persona keeps Save and Discard: a drafted persona is read before it is saved (inv-drafted-answers)."""
    view = _src("components/profile/profile-view.tsx")
    assert "hidden={sections.tile !== tile.id}" in view
    assert "{tiles[tile.id].panel}" in view
    persona = _src("components/profile/how-you-come-across.tsx")
    assert "onClick={() => saveOnce(value)}" in persona and "Discard" in persona
    others = [p for p in (_FRONTEND / "components/profile").glob("*.tsx") if p.name != "how-you-come-across.tsx"]
    for path in others:
        assert "saveOnce(" not in path.read_text(encoding="utf-8"), path.name


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
    assert "const missing = missingAnswers(profile, market.apply_in, markets, market.home);" in nxt
    assert "Never guessed for you" in nxt
    assert "Work-permit and diversity answers only ever come from you." in nxt
    # Diversity is answered in its fold, beside its consent (D10): Next up only opens it.
    assert 'if (current.kind === "diversity") {' in nxt and "onClick: onOpenDiversity" in nxt
    assert "update(SURFACE, (profileNow) =>" in nxt


# ------------------------------------------------------------------------------- The folds

def test_diversity_sits_with_its_consent_and_only_where_a_set_is_checked():
    fold = _src("components/profile/diversity.tsx")
    assert "return m?.offers_eeo ? [m.label] : [];" in fold
    assert '<div id="autofill-eeo">' in fold and '<Fold title="Diversity questions"' in fold
    consent = _src("components/profile/diversity-consent.tsx")
    switch = _between(consent, "export function DiversityConsentSwitch(", "\n}\n")
    # The consent date beside the switch, the server-owned stamp (`acknowledged_at` sent empty on a yes).
    assert "{consent.enabled ? <AgreedOn consent={consent} /> : null}" in switch
    assert "acknowledged_at: enabled ? null : consent.acknowledged_at," in consent
    eligibility = _src("components/profile/eligibility.tsx")
    assert '<div id="autofill-eligibility">' in eligibility and 'title="Eligibility"' in eligibility


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
    """Profile rendered with seeded reads: the header, Next up, the tiles, work permits per country, the folds."""
    result = run_node_render_test("components/profile/profile-view.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr
