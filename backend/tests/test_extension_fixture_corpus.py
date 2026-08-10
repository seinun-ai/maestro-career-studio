"""The control-shape fixture corpus: its safety guard, and what it does TODAY.

`tests/fixtures/autofill/*.json` reconstructs the live ATS control shapes the
extension currently fails on, from telemetry signatures rather than captured
DOM (that directory's README says why). Three kinds of test live here:

1. A PII guard over the raw fixture text. The signatures are value-free by
   schema, so today it can only fail if someone hand-captures a page — which is
   exactly the future author it exists for.
2. A round trip: every fixture loads and runs, so a malformed one fails here
   and names itself instead of surfacing as a baffling assertion inside the
   task that consumes it.
3. Characterisation. Each fixture's docstring pins what today's code does and
   names the task that will CHANGE it. These assertions are meant to be edited:
   the diff on this file is the record of what each writer actually fixed. They
   assert what happens, not what should happen — several of them pin behaviour
   that is plainly wrong.
"""

import re

import pytest

from tests.extension_harness import (
    FIXTURE_DIR,
    fixture_names,
    fixture_paths,
    load_fixture,
    outcome_pairs,
    read_fixture,
    run_fixture,
)


# ---------- 1. the PII guard ----------

# Each entry is (what it catches, pattern). Absolute, not allowlisted: an
# exemption for "example.com" is the crack a real address eventually arrives
# through, and a guard nobody trusts gets deleted. A fixture that genuinely
# needs contact details passes them at the call site instead —
# `run_fixture(tmp_path, name, profile={...})` replaces the fixture's profile.
_PII_PATTERNS = [
    ("an email address or social handle", re.compile(r"@")),
    ("an international dialling prefix", re.compile(r"\+1")),
    ("an HTML value attribute", re.compile(r"value\s*=")),
    ("a LinkedIn profile URL", re.compile(r"linkedin\.com/in/", re.I)),
    # Five, not seven: it has to catch a postcode as well as a phone number or
    # an SSN, and nothing legitimate in an ATS label runs that long — the
    # longest real one in the corpus is Oracle's four-digit `rcf3214`.
    ("a long digit run (phone, postcode, ID)", re.compile(r"\d{5,}")),
    # Catches a pasted `copy(el.outerHTML)` outright, whatever it contains.
    ("raw HTML markup", re.compile(r"<[A-Za-z/!]")),
]


def scan_for_pii(text: str) -> list[str]:
    """Names of every PII pattern `text` trips. Separate from the file walk so
    the guard can be tested against a known-bad payload — see
    `test_the_pii_guard_actually_rejects_a_captured_field`."""
    return [
        what for what, pattern in _PII_PATTERNS if pattern.search(text)
    ]


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_no_fixture_carries_personal_data(path):
    """No fixture may contain a value, let alone a real one.

    Kept even though telemetry signatures are value-free by construction:
    these fixtures ship in the public repository, so a fixture that acquires a
    real value is published along with it.

    Scans the raw text, not the parsed scenario — a value pasted into a
    `reconstructed` note is just as published as one in a field spec.
    """
    hits = scan_for_pii(path.read_text(encoding="utf-8"))
    assert not hits, (
        f"{path.name} looks like it contains {', '.join(hits)}. Fixtures are "
        f"built from telemetry signatures, never from captured DOM — see "
        f"{FIXTURE_DIR.name}/README.md."
    )


def test_the_pii_guard_actually_rejects_a_captured_field():
    """The guard-of-the-guard. A guard that cannot fail is not a guard, and
    every real fixture passes it, so nothing else here would notice if
    `scan_for_pii` were gutted to `return []`."""
    captured = (
        '{"fields": [{"label": "email | applicant_email",'
        ' "value": "jordan.example@mail.test"}]}'
    )
    assert "an email address or social handle" in scan_for_pii(captured)
    assert scan_for_pii('<input name="phone" value="+1 555 0142">')
    assert "a long digit run (phone, postcode, ID)" in scan_for_pii('"98109-4823"')
    assert "a LinkedIn profile URL" in scan_for_pii('"https://linkedin.com/in/sample"')
    # ...and stays quiet on the shapes the corpus legitimately holds.
    assert scan_for_pii("workexperience-192--currentlyworkhere") == []
    assert scan_for_pii("-1_personprofilefields.rcf3214_year | from") == []


def test_the_corpus_holds_only_json_fixtures_and_its_readme():
    """The guard scans `*.json`. A captured page dropped into the directory as
    `capture.html` would otherwise be published unscanned."""
    stray = sorted(
        p.name for p in FIXTURE_DIR.iterdir()
        if p.suffix != ".json" and p.name != "README.md"
    )
    assert stray == [], f"unscanned files in the fixture corpus: {stray}"


# ---------- 2. round trip ----------


def test_the_corpus_is_not_empty():
    """`fixture_paths()` is parametrized at collection time; an empty glob
    turns every guard above into zero tests that pass."""
    assert len(fixture_names()) >= 4


@pytest.mark.parametrize("name", fixture_names())
def test_every_fixture_loads_and_runs(tmp_path, name):
    """A malformed fixture fails HERE, naming itself, rather than inside the
    task that consumes it. `read_fixture` does the structural validation
    (unknown keys, duplicate labels, verbatim citations that no field carries);
    this proves the result is something the extension can actually be run
    against."""
    read_fixture(name)
    result = run_fixture(tmp_path, name)
    assert "observations" in result
    labels = {field["label"] for field in load_fixture(name)["fields"]}
    for observation in result["observations"]:
        assert observation["label"] in labels, (
            f"{name}: observation for {observation['label']!r} matches no "
            f"declared field — the harness label remap did not resolve it"
        )


# ---------- 3. characterisation ----------


def test_workday_employment_block_today(tmp_path):
    """TODAY: every field of both visible blocks is answered, checkbox included.

    Task 11 took the last `no_rule` here — "I currently work here" — and split
    it in two, which is the point of a DERIVED answer rather than a written one.
    Block 192's job has no end date, so its box is ticked and reported `filled`.
    Block 214's ended in 2021, so its box is `skipped_checkbox`: recognised,
    derived to "no", and deliberately not touched. Ticking that one would be a
    false statement on a record an employer can verify, so the untouched box is
    the more important half of the assertion below.

    Task 9 (block-scoped resolution) took Location from `no_rule` to `filled`,
    which needed BOTH halves of the fix: a rule that recognises an employment
    block's Location, and a `location` key in
    `routers/autofill._employment_blocks`, which had none — a perfect rule would
    have had nothing to write.

    Company was `no_rule` here and is now `filled`, but nothing about the RULE
    changed for Workday: the fixture's label was a reconstruction, and it was
    wrong. Workday emits "company* | companyname | …--companyname", which
    `company\\s*name` has always matched. The bare "Company" that never fills is
    real and belongs to Siemens — see the fixture's `reconstructed` note, and
    `test_extension_block_scope.test_a_bare_company_label_fills_the_employer`
    for the rule that now covers it.

    Task 8 (date-part writer) changed the VALUES and not one outcome: the month
    inputs held the English month name "March" and the year inputs held the
    year only because this fixture carried ISO dates, which
    /api/autofill/employment-blocks never returns. Against the real "Mon YYYY"
    payload nothing here parsed at all, and the live signatures show what
    actually happened — `emp-start-date`/`emp-end-date` claiming all four
    spinners and reporting not_stuck.

    Three things here are RIGHT and must survive later tasks:
    * the hidden prototype block consumes no resume entry — every visible block
      still gets its own, which is the exact property a block-ordinal scheme
      would break;
    * block 192 gets employment entry 0 and block 214 gets entry 1;
    * entry 0 is current, so its two To fields are skipped silently rather than
      being written "Present" or reported as a failure.
    """
    result = run_fixture(tmp_path, "workday_employment_block")

    assert outcome_pairs(result) == [
        # The hidden prototype block. Only rule-matched fields are logged, and
        # none of them consume a resume entry — the block claims no entry at
        # all, so the two rules Task 9 taught to match here (Company, Location)
        # added observations without disturbing anything below.
        ("job title* | jobtitle | workexperience-0--jobtitle", "hidden"),
        ("company* | companyname | workexperience-0--companyname", "hidden"),
        ("location | location | workexperience-0--location", "hidden"),
        ("i currently work here | currentlyworkhere | workexperience-0--currentlyworkhere", "hidden"),
        ("month | workexperience-0--startdate-datesectionmonth-input | from*", "hidden"),
        ("year | workexperience-0--startdate-datesectionyear-input | from*", "hidden"),
        ("month | workexperience-0--enddate-datesectionmonth-input | to*", "hidden"),
        ("year | workexperience-0--enddate-datesectionyear-input | to*", "hidden"),
        ("role description | workexperience-0--roledescription", "hidden"),
        # Block 1 → employment entry 0 (current).
        ("job title* | jobtitle | workexperience-192--jobtitle", "filled"),
        ("company* | companyname | workexperience-192--companyname", "filled"),
        ("location | location | workexperience-192--location", "filled"),
        # Derived: this job has no end date, so the box is ticked.
        ("i currently work here | currentlyworkhere | workexperience-192--currentlyworkhere", "filled"),
        ("month | workexperience-192--startdate-datesectionmonth-input | from*", "filled"),
        ("year | workexperience-192--startdate-datesectionyear-input | from*", "filled"),
        # The two To fields emit NOTHING: entry 0 is current, so the list slot
        # is consumed with an empty value and the loop moves on. Deliberate —
        # see test_a_block_past_the_end_of_the_list_reports_nothing.
        ("role description | workexperience-192--roledescription", "filled"),
        # Block 2 → employment entry 1 (ended), so its To fields do fill.
        ("job title* | jobtitle | workexperience-214--jobtitle", "filled"),
        ("company* | companyname | workexperience-214--companyname", "filled"),
        ("location | location | workexperience-214--location", "filled"),
        # …and derived the other way for the job that ended: recognised, and
        # left exactly as the page rendered it.
        ("i currently work here | currentlyworkhere | workexperience-214--currentlyworkhere", "skipped_checkbox"),
        ("month | workexperience-214--startdate-datesectionmonth-input | from*", "filled"),
        ("year | workexperience-214--startdate-datesectionyear-input | from*", "filled"),
        ("month | workexperience-214--enddate-datesectionmonth-input | to*", "filled"),
        ("year | workexperience-214--enddate-datesectionyear-input | to*", "filled"),
        ("role description | workexperience-214--roledescription", "filled"),
    ]

    values = result["values"]
    # Entries land in block order, and — the part Task 9 made true — EVERY
    # field of a block now names the same job. Under the per-rule counter they
    # could disagree, and on directsupply.wd501 they did.
    assert values["job title* | jobtitle | workexperience-192--jobtitle"] == (
        "Senior Data Scientist")
    assert values["company* | companyname | workexperience-192--companyname"] == (
        "Northwind Traders")
    assert values["location | location | workexperience-192--location"] == "Austin, TX"
    assert values["job title* | jobtitle | workexperience-214--jobtitle"] == (
        "Data Scientist")
    assert values["company* | companyname | workexperience-214--companyname"] == (
        "Contoso Ltd")
    assert values["location | location | workexperience-214--location"] == "Dallas, TX"
    # A Workday month input wants "03", and gets it — narrowed out of the
    # payload's "March 2021" at write time, once the control is known.
    assert values["month | workexperience-192--startdate-datesectionmonth-input | from*"] == "03"
    assert values["year | workexperience-192--startdate-datesectionyear-input | from*"] == "2021"
    assert values["month | workexperience-214--enddate-datesectionmonth-input | to*"] == "02"
    # Nothing at all reached the hidden prototype.
    assert values["job title* | jobtitle | workexperience-0--jobtitle"] == ""
    assert values["company* | companyname | workexperience-0--companyname"] == ""
    assert values["location | location | workexperience-0--location"] == ""
    # The tick lands on the current job and NOWHERE else — not on the job that
    # ended, and not on the hidden prototype, which claims no entry at all.
    checked = result["checked"]
    assert checked[
        "i currently work here | currentlyworkhere | workexperience-192--currentlyworkhere"
    ] is True
    assert checked[
        "i currently work here | currentlyworkhere | workexperience-214--currentlyworkhere"
    ] is False
    assert checked[
        "i currently work here | currentlyworkhere | workexperience-0--currentlyworkhere"
    ] is False


def test_workday_education_dates_today(tmp_path):
    """TODAY: every field in the block fills, year widgets included.

    Both years reported `no_rule` until Task 8. `edu-start-year`/`edu-end-year`
    wanted the literal "education start year"/"end year"; the rules now also
    read Workday's own vocabulary, "firstyearattended"/"lastyearattended".
    The employment year rules that WOULD match ("...attended-datesectionyear"
    contains "end...year") are still correctly held off by their `not:` guard —
    `test_an_employment_rule_still_cannot_reach_an_education_block` is the half
    of that which fails loudly if the guard goes.

    School, Degree and Field of Study filled before and after: they are the
    positive controls proving Task 8 did not disturb the block around the
    fields it fixed.
    """
    result = run_fixture(tmp_path, "workday_education_dates")

    assert outcome_pairs(result) == [
        ("school or university | education-193--school", "filled"),
        ("degree | education-193--degree", "filled"),
        ("field of study | education-193--fieldofstudy", "filled"),
        ("year | education-193--firstyearattended-datesectionyear-input | from", "filled"),
        ("year | education-193--lastyearattended-datesectionyear-input | to (actual or expected)", "filled"),
    ]
    values = result["values"]
    assert values["school or university | education-193--school"] == (
        "Northern Institute of Technology")
    assert values["year | education-193--firstyearattended-datesectionyear-input | from"] == "2016"
    assert values[
        "year | education-193--lastyearattended-datesectionyear-input | to (actual or expected)"
    ] == "2018"


def test_oracle_opaque_year_today(tmp_path):
    """TODAY: the year and month parts fill; the day parts report their gap.

    All six reported `no_rule` and stayed empty until Task 8. The labels are a
    generated identifier repeated twice and the container text names the
    SECTION, not the field, so nothing in either label distinguishes the
    from-date from the to-date — DOM order is the only signal there is, and no
    rule read it.

    Three separate decisions are pinned here, and each is the interesting half
    of one of them:

    * the month select takes **"Jul"**, not "07" and not "July" — Oracle's own
      option list is Jan…Dec, and the writer matches against it rather than
      picking a house format;
    * the year fields take 2018 then 2021 in DOM order, From before To, from
      the single employment entry;
    * the day selects report `missing_source`, not a guess. Neither source
      carries a day, and picking the 1st would state a start date the user
      never gave. `no_rule` would have been a lie in the other direction: we
      know exactly what the control is.
    """
    result = run_fixture(tmp_path, "oracle_opaque_year")

    assert outcome_pairs(result) == [
        ("month | -1_personprofilefields.rcf3214_month | -1_personprofilefields.rcf3214_month | professional experience (1)* required. | month", "filled"),
        ("day | -1_personprofilefields.rcf3214_date | -1_personprofilefields.rcf3214_date | professional experience (1)* required. | day", "missing_source"),
        ("-1_personprofilefields.rcf3214_year | -1_personprofilefields.rcf3214_year | professional experience (1)* required.", "filled"),
        ("month | -1_personprofilefields.rcf3215_month | -1_personprofilefields.rcf3215_month | professional experience (1)* required. | month", "filled"),
        ("day | -1_personprofilefields.rcf3215_date | -1_personprofilefields.rcf3215_date | professional experience (1)* required. | day", "missing_source"),
        ("-1_personprofilefields.rcf3215_year | -1_personprofilefields.rcf3215_year | professional experience (1)* required.", "filled"),
    ]
    values = result["values"]
    assert values[
        "month | -1_personprofilefields.rcf3214_month | -1_personprofilefields.rcf3214_month | professional experience (1)* required. | month"
    ] == "Jul"
    assert values[
        "-1_personprofilefields.rcf3214_year | -1_personprofilefields.rcf3214_year | professional experience (1)* required."
    ] == "2018"
    assert values[
        "-1_personprofilefields.rcf3215_year | -1_personprofilefields.rcf3215_year | professional experience (1)* required."
    ] == "2021"
    assert values[
        "day | -1_personprofilefields.rcf3214_date | -1_personprofilefields.rcf3214_date | professional experience (1)* required. | day"
    ] == "", "a day was invented for a date that carries none"


def test_workday_skills_token_today(tmp_path):
    """TODAY: every skill on the resume becomes its own token.

    This reported `no_rule` and was never written until Task 10, and the two
    things that made it hard are both still visible here. The kind is `text`,
    not `combobox` — telemetry recorded `text`, so `isCombobox()` returned false
    on the live page and routing this through `fillCombobox` would never have
    run. And the AI fallback could not rescue it either: its deny-list regex
    matches both "search" and "location", so the field was excluded there too.

    The box is EMPTY afterwards and that is the success, not the failure: each
    value was consumed into a chip. It is also why this needed its own commit
    ladder — `valueHolds` asks whether the value is still in the box, and the
    answer to that is no on every write that worked.

    Task 10 also moved where the answer comes from. The fixture used to declare
    a top-level `skills` key in the PROFILE, invented and labelled as a
    proposal; the live profile has no such key and never did. Skills come from
    the resume, so the fixture now declares them as a scenario input of their
    own.
    """
    result = run_fixture(tmp_path, "workday_skills_token")

    assert outcome_pairs(result) == [
        ("type to add skills | search | skills--skills", "filled"),
    ]
    assert result["observations"][0]["kind"] == "text"
    assert result["observations"][0]["rule_id"] == "skills"
    assert result["tokens"]["type to add skills | search | skills--skills"] == [
        "Python", "SQL", "Experiment design",
    ]
    assert result["values"]["type to add skills | search | skills--skills"] == ""
    # Under the cap, so the report carries no hedge — and the profile beside it
    # supplies no skills, which is the point: it is not a source of them.
    assert result["filled"] == [
        {"label": "type to add skills | search | skills--skills",
         "value": "Python, SQL, Experiment design"},
    ]


def test_eeo_race_options_today(tmp_path):
    """TODAY: race checkboxes whose label carries no EEO keyword report
    `no_rule`, even with the EEO opt-in ON and the exact categories supplied.

    Task 6 left this deliberately: nothing in "american indian or alaska native
    | dq-option-7 | american indian or alaska native" marks it as a
    protected-class question, and `isEeoLabel` keys on the words
    veteran/disab/hispanic/gender/sex/race/ethnic. Task 9 is the fix.

    The important half is what does NOT happen: no box is ticked, and
    `eeoFilled` is empty. A writer that starts recognising these must keep
    "White" — a category this user did not claim — unticked.
    """
    result = run_fixture(tmp_path, "eeo_race_options")

    assert outcome_pairs(result) == [
        ("american indian or alaska native | dq-option-7 | american indian or alaska native", "no_rule"),
        ("asian | dq-option-8 | asian", "no_rule"),
        ("white | dq-option-9 | white", "no_rule"),
    ]
    assert not any(result["checked"].values())
    assert result["eeoFilled"] == []
    # Not `eeo_disabled` either, with the opt-in off: the label is invisible to
    # the EEO detector in both directions, so turning the setting off changes
    # nothing. Pinned because it is the cheapest way to tell a future reader
    # that the opt-in is not what is holding this field back.
    off = run_fixture(tmp_path, "eeo_race_options", eeo_enabled=False)
    assert [outcome for _, outcome in outcome_pairs(off)] == ["no_rule"] * 3


def test_icims_signature_today(tmp_path):
    """TODAY: the iCIMS e-signature control reports `policy_blocked`.

    The one fixture no later task may change. HR-3 is recognised-and-never-
    written, and the deny-list runs ahead of the EEO opt-in, rule matching and
    the visibility gate precisely so no writer added later can reach it. The
    checkbox is untouched, which for a tick box is the whole point: `click()`
    toggles, so "we did nothing" and "we signed it" differ by one call.
    """
    result = run_fixture(tmp_path, "icims_signature")

    assert outcome_pairs(result) == [
        ("signature | icims_f_signature | icims_f_signature", "policy_blocked"),
    ]
    assert result["observations"][0]["rule_id"] is None
    assert result["checked"]["signature | icims_f_signature | icims_f_signature"] is False
    assert result["filled"] == []
