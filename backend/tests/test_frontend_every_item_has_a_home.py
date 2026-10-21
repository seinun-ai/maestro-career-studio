"""Pins: every one of today's 156 Profile and Settings items keeps a home (design refresh Goal Card; Tasks 7.1-7.3).

The "Where everything lives" board (the Map board) lists 156 items: 12 under "Setup, first run only", 62
under Profile and 82 under the four Settings groups. A board label is the board's own description of an
item; its needles are the words the screen says for it, or the stable keys that render them. Each item is
looked for in the files of the tile, fold or step that holds it (a needle given as `(path, text)` is a home
outside them, the path from the repo root). Source and needles are compared with whitespace collapsed, so a
needle can span a JSX line break.

- **Settings, 82:** `test_frontend_settings_refresh.py`'s table, counted here, not copied.
- **Profile, 62:** one row per board item, grouped by the tile or fold the board names
  (`lib/profile-tiles.ts`), plus Saving. The field table the tiles render (labels, options) is
  `lib/autofill-options.ts`, so it joins every tile's files; the row's other needle is the tile rendering
  that group. A work-permit question is worded per country from its market's `work_auth_vocab`, so its row
  pins the key, and `test_each_country_is_asked_every_work_permit_key` pins that each country you apply in
  is asked it. "Countries authorized" is no field any more: the fill derives it from each country's
  `authorized_now` and You apply in (`services/autofill_country.py`, `test_autofill_country.py`).
- **Setup, 12:** one row per board item, grouped by the step that asks it (`SETUP_STEPS`); Run setup
  again is Settings › Basics' About footer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import test_frontend_settings_refresh as settings
from tests.node_ts import ts_map

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"

Needle = str | tuple[str, str]


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _missing(needles: tuple[Needle, ...], src: str) -> list[Needle]:
    """The needles not found: a string in `src` (already flat), a `(path, text)` in that file."""
    out = []
    for needle in needles:
        if isinstance(needle, tuple):
            path, text = needle
            if _flat(text) not in _flat((_ROOT / path).read_text(encoding="utf-8")):
                out.append(needle)
        elif _flat(needle) not in src:
            out.append(needle)
    return out


# --------------------------------------------------------------------------------- Profile

# The files each tile or fold renders from (its card and editor), by its title in lib/profile-tiles.ts.
_PROFILE_FILES: dict[str, tuple[str, ...]] = {
    "Contact": ("components/profile/contact.tsx",),
    "Where you apply": ("components/profile/where-you-apply.tsx",),
    "Work permits": ("components/profile/work-permits.tsx",),
    "Jobs you want": ("components/profile/jobs-you-want.tsx",),
    "How you come across": ("components/profile/how-you-come-across.tsx",),
    "Start and pay": ("components/profile/start-and-pay.tsx",),
    "Education": ("components/profile/education.tsx",),
    "Languages": ("components/profile/languages.tsx",),
    "Your own questions": ("components/profile/own-questions.tsx",),
    "Diversity questions": ("components/profile/diversity.tsx", "components/profile/diversity-consent.tsx"),
    "Eligibility": ("components/profile/eligibility.tsx",),
    # Not a tile: the one provider every answer editor saves through, and the status each one shows.
    "Saving": ("components/profile/autofill-profile.tsx", "components/settings/autosave-status.tsx"),
}
_FIELD_TABLE = "lib/autofill-options.ts"

_PERSONAL = 'fields={groupFields("personal")}'
_PREFERENCES = 'fields={groupFields("preferences")}'
_EEO = 'fields={groupFields("eeo")}'
_ELIGIBILITY = 'const fields = groupFields("eligibility");'
_PERMITS = ("applyIn.map((key) => {", "workPermitFields(market?.work_auth_vocab)")
_APPLY_IN = ("frontend/components/profile/where-you-apply.tsx", "You apply in </span>")

# (tile or fold, board label, needles)
_PROFILE: list[tuple[str, str, tuple[Needle, ...]]] = [
    ("Contact", "First name", ('{ key: "first_name", label: "First name" }', _PERSONAL)),
    ("Contact", "Last name", ('{ key: "last_name", label: "Last name" }', _PERSONAL)),
    ("Contact", "Email", ('{ key: "email", label: "Email" }', _PERSONAL)),
    ("Contact", "Phone", ('{ key: "phone", label: "Phone" }', _PERSONAL)),
    ("Contact", "Street address", ('{ key: "address", label: "Street address" }', _PERSONAL)),
    ("Contact", "Address line 2", ('{ key: "address_2", label: "Address line 2", optional: true }', _PERSONAL)),
    ("Contact", "City", ('{ key: "city", label: "City" }', _PERSONAL)),
    ("Contact", "State", ('{ key: "state", label: "State" }', _PERSONAL)),
    ("Contact", "Postal code", ('{ key: "postal_code", label: "Postal code" }', _PERSONAL)),
    ("Contact", "Country", ('{ key: "country", label: "Country" }', _PERSONAL)),
    ("Contact", "LinkedIn profile link", ('{ key: "linkedin", label: "LinkedIn profile link" }', _PERSONAL)),
    ("Contact", "GitHub link", ('{ key: "github", label: "GitHub link" }', _PERSONAL)),
    ("Contact", "Website", ('{ key: "website", label: "Website" }', _PERSONAL)),
    ("Contact", "Fill from career history", ('"Fill from career history"', "onClick={fillFromResume}")),
    ("Where you apply", "You live in", ("<Label htmlFor={homeId}>You live in</Label>",)),
    ("Where you apply", "You apply in", ("You apply in </span>", "onClick={() => toggleCountry(m.key)}")),
    # Work permits, one set per country, each in its market's words: the keys, not the US wording.
    ("Work permits", "Work authorization status", ('{ key: "status", label: "Work authorization status" }', *_PERMITS)),
    ("Work permits", "Authorized to work now?", ('key: "authorized_now"', *_PERMITS)),
    ("Work permits", "Need visa sponsorship now?", ('key: "sponsorship_now"', *_PERMITS)),
    ("Work permits", "Need visa sponsorship later?", ('key: "sponsorship_future"', *_PERMITS)),
    ("Work permits", "Authorization expires on",
     ('key: "authorization_expires_on", label: "Authorization expires on"', *_PERMITS)),
    ("Work permits", "Countries authorized", (
        'key: "authorized_now"', *_PERMITS, _APPLY_IN,
        ("backend/app/services/autofill_country.py", "derived = _authorized_countries(entries)"),
        ("backend/app/services/autofill_country.py", "if autofill_profile.typed_work_auth(raw).authorized_now is True:"),
    )),
    ("Jobs you want", "Roles you want", ('<Label htmlFor="job-preferences-roles" optional> Roles you want </Label>',)),
    ("Jobs you want", "Years of experience",
     ('<Label htmlFor="job-preferences-years" optional> Years of experience </Label>',)),
    ("Jobs you want", "Work location", ('<Label htmlFor="job-preferences-remote" optional> Work location </Label>',)),
    ("Jobs you want", "Locations", ('<Label htmlFor="job-preferences-locations" optional> Locations </Label>',)),
    ("Jobs you want", "Minimum salary, in your currency", (
        '<Label htmlFor="job-preferences-min-salary" optional> Minimum salary </Label>',
        "const salaryCurrency = minSalary?.currency ?? money.home ?? null;",
        '<SelectTrigger aria-label="Currency"',
    )),
    ("Jobs you want", "Job types", ("<Label id={employmentLabelId} optional> Job types </Label>",)),
    ("How you come across", "Persona", ('aria-label="Persona"',)),
    ("How you come across", "Draft from my career history",
     ("Draft from my career history", "onClick={() => draftOnce(editRevision.current)}")),
    ("Start and pay", "Desired salary", ('{ key: "desired_salary", label: "Desired salary" }', _PREFERENCES)),
    ("Start and pay", "Notice period", ('{ key: "notice_period", label: "Notice period"', _PREFERENCES)),
    ("Start and pay", "Earliest start date", ('{ key: "earliest_start_date", label: "Earliest start date" }', _PREFERENCES)),
    ("Start and pay", "Willing to relocate?", ('key: "willing_to_relocate", label: "Willing to relocate?"', _PREFERENCES)),
    ("Start and pay", "How did you hear about the job?",
     ('{ key: "how_heard", label: "How did you hear about the job?" }', _PREFERENCES)),
    ("Education", "School", ('{ key: "school", label: "School" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "Degree", ('{ key: "degree", label: "Degree" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "Major", ('{ key: "discipline", label: "Major" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "GPA", ('{ key: "gpa", label: "GPA" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "Start year", ('{ key: "start_year", label: "Start year" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "Graduation year", ('{ key: "end_year", label: "Graduation year" }', "{EDUCATION_FIELDS.map((field) => {")),
    ("Education", "Add education", ("Add education", "onClick={() => setEducation([...education, {}])}")),
    ("Languages", "Language", ('{ key: "language", label: "Language" }', "{LANGUAGE_FIELDS.map((field) => {")),
    # Each level is a select of the words forms offer (LANGUAGE_LEVELS: Basic, Intermediate, Fluent).
    ("Languages", "Reading level",
     ('{ key: "read", label: "Reading", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] }',
      "{LANGUAGE_FIELDS.map((field) => {")),
    ("Languages", "Speaking level",
     ('{ key: "speak", label: "Speaking", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] }',
      "{LANGUAGE_FIELDS.map((field) => {")),
    ("Languages", "Writing level",
     ('{ key: "write", label: "Writing", type: "select", options: [NOT_SET, ...LANGUAGE_LEVELS] }',
      "{LANGUAGE_FIELDS.map((field) => {")),
    ("Languages", "Add language", ("Add language", "onClick={() => setLanguages([...languages, {}])}")),
    ("Your own questions", "Question and answer", (
        "<Label htmlFor={`af-custom-${i}-question`}>Question</Label>",
        "<Label htmlFor={`af-custom-${i}-answer`}>Answer</Label>",
    )),
    ("Your own questions", "Add question",
     ("Add question", 'onClick={() => setCustom([...custom, { question: "", answer: "" }])}')),
    # Diversity, folded, with its consent beside the answers it covers (D10).
    ("Diversity questions", "Let the Companion fill these answers",
     ("Let the Companion fill these answers", "<DiversityConsentSwitch")),
    ("Diversity questions", "Consent date and policy", (
        "{consent.enabled ? <AgreedOn consent={consent} /> : null}",
        ("frontend/components/settings/companion-fill-section.tsx",
         "You agreed on {formatAbsoluteDateTime(consent.acknowledged_at)}"),
        ("frontend/components/settings/companion-fill-section.tsx", "` (policy ${consent.policy_version})`"),
    )),
    ("Diversity questions", "Are you a veteran?", ('key: "veteran_status", label: "Are you a veteran?"', _EEO)),
    ("Diversity questions", "Disability status", ('key: "disability_status", label: "Disability status"', _EEO)),
    ("Diversity questions", "Gender", ('key: "gender", label: "Gender"', _EEO)),
    ("Diversity questions", "How you describe your gender",
     ('key: "gender_self_describe", label: "How you describe your gender"', _EEO)),
    ("Diversity questions", "Hispanic or Latino?", ('key: "hispanic_latino", label: "Hispanic or Latino?"', _EEO)),
    ("Diversity questions", "Race or ethnicity", ('key: "race_ethnicity", label: "Race or ethnicity"', _EEO)),
    ("Diversity questions", "Decline the rest", ("Decline the rest", "onClick={declineAllEeo}")),
    ("Eligibility", "Are you 18 or older?", ('key: "over_18", label: "Are you 18 or older?"', _ELIGIBILITY)),
    ("Eligibility", "Worked for this company before?",
     ('key: "previously_employed_here", label: "Have you worked for the company you\'re applying to?"', _ELIGIBILITY)),
    ("Eligibility", "Subject to a restrictive covenant?",
     ('key: "non_compete",', 'label: "Subject to a restrictive covenant?"', _ELIGIBILITY)),
    ("Saving", "Saves as you go", ("const answers = useAutosave<Profile>(initial,", "Saving…", "Not saved")),
]

# The board's Profile sections and how many items each lists.
_PROFILE_COUNTS = {
    "Contact": 14, "Where you apply": 2, "Work permits": 6, "Jobs you want": 6, "How you come across": 2,
    "Start and pay": 5, "Education": 7, "Languages": 5, "Your own questions": 2, "Diversity questions": 9,
    "Eligibility": 3, "Saving": 1,
}


def _profile_source(section: str) -> str:
    return _flat("\n".join(_read(rel) for rel in (*_PROFILE_FILES[section], _FIELD_TABLE)))


@pytest.mark.parametrize(("section", "label", "needles"), _PROFILE, ids=[f"{s}: {lbl}" for s, lbl, _ in _PROFILE])
def test_every_profile_item_has_a_home_in_its_tile(section: str, label: str, needles: tuple[Needle, ...]):
    missing = _missing(needles, _profile_source(section))
    assert not missing, (section, label, missing)


def test_the_profile_sections_are_the_tiles_and_folds():
    """The board's sections are Profile's nine tiles and two folds, in order, then Saving."""
    lib = _read("lib/profile-tiles.ts")
    titles = re.findall(r'\{ id: "\w+", title: "([^"]+)"', lib)
    assert list(_PROFILE_FILES) == [*titles, "Saving"]
    assert [section for section, _, _ in _PROFILE] == sorted(
        (section for section, _, _ in _PROFILE), key=list(_PROFILE_FILES).index
    )


def test_each_country_is_asked_every_work_permit_key():
    """Every vocabulary asks the three yes/no keys and when the permit runs out; only `us_visa` asks the
    status. Profile asks one set per country you apply in, Setup one card per country."""
    vocabs = ["us_visa", "uk", "generic", "a market with no vocabulary yet"]
    asked = [[field["key"] for field in fields] for fields in ts_map(str(_FRONTEND / _FIELD_TABLE), "workPermitFields", vocabs)]
    keys = ["authorized_now", "sponsorship_now", "sponsorship_future", "authorization_expires_on"]
    assert asked == [["status", *keys], keys, keys, keys]
    tile = _flat(_read("components/profile/work-permits.tsx"))
    assert all(needle in tile for needle in _PERMITS)
    setup = _flat(_read("lib/setup-flow.ts"))
    assert 'applyIn.map((market) => ({ kind: "permit",' in setup
    assert "vocab: byKey.get(market)?.work_auth_vocab," in setup


# ----------------------------------------------------------------------------------- Setup

# The files each step renders from, by its title in lib/setup-flow.ts `SETUP_STEPS`; the component the
# flow renders for it (components/setup/setup-flow.tsx).
_SETUP_FILES: dict[str, tuple[str, ...]] = {
    "AI model": ("components/setup/setup-model-step.tsx",),
    "Your resume": (
        "components/setup/setup-resume-step.tsx", "components/setup/dropzone.tsx", "components/setup/use-resume-import.ts",
    ),
    "Where and what": ("components/setup/setup-where-step.tsx",),
    "Form answers": ("components/setup/setup-answers-step.tsx", "lib/setup-flow.ts", "lib/setup-answers.ts"),
}
_STEP_COMPONENTS = {
    "AI model": 'case "model": return <SetupModelStep',
    "Your resume": 'case "resume": return <SetupResumeStep',
    "Where and what": 'case "where": return <SetupWhereStep',
    "Form answers": 'case "answers": return ( <SetupAnswersStep',
}
_ABOUT = "Settings › Basics"

# (step, board label, needles)
_SETUP: list[tuple[str, str, tuple[Needle, ...]]] = [
    ("AI model", "AI provider", ('aria-label="AI provider"', "{CARDS.map((c) => (", "<Radio value={c.id} />")),
    ("AI model", "API key and Test", (
        "label={`${card.name} API key`}", "onClick={() => void test()}> Test </Button>", '"/api/settings/openai/probe"',
    )),
    ("Your resume", "Import resume", (
        "Bring your resume", "void importer.run(picked)", '"Choose or drop a file"', "kbImportResume(file, false)",
    )),
    ("Where and what", "You live in", ("<Label htmlFor={homeId}>You live in</Label>",)),
    ("Where and what", "You apply in", ("You apply in </span>", "onClick={() => toggleCountry(m.key)}")),
    ("Where and what", "Roles", ('<Label htmlFor="setup-roles">Roles you want</Label>', "From your resumes")),
    ("Where and what", "Work mode", ("Work mode </span>", "{WORK_MODES.map((mode) => {")),
    ("Form answers", "Work permit, per country", (
        'applyIn.map((market) => ({ kind: "permit",', "Work permit </span>",
        "permitQuestions(question.vocab).map((q) => {", "withPermitAnswer(current, question.market, q.key, option.value)",
    )),
    ("Form answers", "Notice period", (
        "How soon could you start?", "<Label htmlFor={noticeId}>Notice period</Label>",
        'withPreference(current, "notice_period", choice)',
    )),
    ("Form answers", "Willing to relocate",
     ("Open to moving for a job?", 'withPreference(current, "willing_to_relocate", answer)')),
    ("Form answers", "Diversity: answer or decline", (
        'rest.push({ kind: "diversity",', '{ value: "answer", label: "Answer them" }',
        '{ value: "decline", label: "Decline the rest" }', "withDiversityDeclined(current)",
    )),
    # The board lists it with Setup; it lives in Settings › Basics' About footer (the plan's Task 7.1).
    (_ABOUT, "Run setup again", ("Run setup again", 'href="/setup"')),
]


def _setup_source(step: str) -> str:
    if step == _ABOUT:
        return _flat(settings._tab_source("basics"))
    return _flat("\n".join(_read(rel) for rel in _SETUP_FILES[step]))


@pytest.mark.parametrize(("step", "label", "needles"), _SETUP, ids=[f"{s}: {lbl}" for s, lbl, _ in _SETUP])
def test_every_setup_item_has_a_home_in_its_step(step: str, label: str, needles: tuple[Needle, ...]):
    missing = _missing(needles, _setup_source(step))
    assert not missing, (step, label, missing)


def test_the_setup_groups_are_the_four_steps_the_flow_renders():
    lib = _read("lib/setup-flow.ts")
    steps = lib[lib.index("export const SETUP_STEPS") : lib.index("];", lib.index("export const SETUP_STEPS"))]
    assert re.findall(r'title: "([^"]+)"', steps) == list(_SETUP_FILES)
    flow = _flat(_read("components/setup/setup-flow.tsx"))
    for step, rendered in _STEP_COMPONENTS.items():
        assert rendered in flow, step
    assert {step for step, _, _ in _SETUP} == {*_SETUP_FILES, _ABOUT}


# ------------------------------------------------------------------------------- The board

def test_the_board_holds_156_items_setup_12_profile_62_settings_82():
    counted = {section: 0 for section in _PROFILE_FILES}
    for section, _, _ in _PROFILE:
        counted[section] += 1
    assert counted == _PROFILE_COUNTS
    settings_items = len(settings._BOARD) + len(settings._CLIENTS)
    assert (len(_SETUP), len(_PROFILE), settings_items) == (12, 62, 82)
    assert len(_SETUP) + len(_PROFILE) + settings_items == 156


def test_no_board_label_is_listed_twice_in_its_group():
    for table in (_SETUP, _PROFILE):
        rows = [(group, label) for group, label, _ in table]
        assert len(rows) == len(set(rows)), [row for row in rows if rows.count(row) > 1]
