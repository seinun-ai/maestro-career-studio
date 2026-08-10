"""Writing ONE PART of a date into a control that asked for exactly that part.

A split date widget — Workday's `…datesectionmonth-input`, Oracle's
`…rcf3214_month` select, iCIMS's `icims_0_startdate_year` — is three controls
holding one date between them. The rules hold whole dates, so every one of
those controls was either unmatched (`no_rule`) or handed the whole date
(`not_stuck`, eight live observations on Workday alone).

Three separate questions have to be answered right, and each has its own
section below:

1. **Which part** the control wants — from the control's `type` first, then the
   vendor's sub-control identifier, then the plain word in the label.
2. **In what format** it wants it — a select's own option list is the answer;
   a plain text spinner gets the ISO two digits.
3. **Whether we have it at all** — a day never, a month only when the source
   date carries one. `missing_source` is the honest answer and the only one
   that does not invent a fact about the user's history.

`test_extension_fixture_corpus.py` pins these same shapes end to end against
the live-signature corpus; this file is where the individual decisions are
argued.
"""

import pytest

from tests.extension_harness import (
    load_fixture,
    outcome_for,
    outcome_pairs,
    run_fixture,
    run_profile_fill,
)


# One job, ended — so both ends of the range have an answer and a wrong one is
# visible. "Mon YYYY" because that is what /api/autofill/employment-blocks
# returns (routers/autofill._employment_blocks passes the resume field through
# verbatim, and the resume model is "Mon YYYY").
_ONE_JOB = [
    {
        "employer": "Contoso Ltd",
        "title": "Data Scientist",
        "start_date": "July 2018",
        "end_date": "February 2021",
        "current": False,
        "description": "Shipped the experimentation platform.",
    }
]

_START_MONTH = "month | workexperience-192--startdate-datesectionmonth-input | from"
_START_YEAR = "year | workexperience-192--startdate-datesectionyear-input | from"
_END_MONTH = "month | workexperience-192--enddate-datesectionmonth-input | to"
_END_YEAR = "year | workexperience-192--enddate-datesectionyear-input | to"


def _workday_dates(**flags):
    """The four Workday date-part inputs of one employment block, alone."""
    return [
        {"label": label, "kind": "text", **flags}
        for label in (_START_MONTH, _START_YEAR, _END_MONTH, _END_YEAR)
    ]


def _month_select(options, label=None):
    return {
        "label": label or _START_MONTH,
        "kind": "select",
        "options": [{"value": text, "textContent": text} for text in options],
    }


# ---------- 1. which part ----------


def test_a_year_control_gets_the_year_and_nothing_else(tmp_path):
    """The Workday education widget the corpus ranks in its top ten failures.

    Both fields are year-only — Workday's education dates have no month sibling
    — and the answers were in the profile the whole time.
    """
    result = run_fixture(tmp_path, "workday_education_dates")
    values = result["values"]

    assert values[
        "year | education-193--firstyearattended-datesectionyear-input | from"
    ] == "2016"
    assert values[
        "year | education-193--lastyearattended-datesectionyear-input"
        " | to (actual or expected)"
    ] == "2018"


def test_the_sub_control_identifier_is_read_where_a_plain_word_cannot_be(tmp_path):
    """"datesectionyear" and "rcf3214_year" carry no word boundary before
    "year" — "n" and "_" are both word characters — so a `\\byear\\b` pattern
    matches neither. Every date part in the corpus is named one of those two
    ways, so matching the identifier forms is the whole ballgame, not a nicety.

    Every label here is deliberately stripped of any standalone part WORD, so
    the identifier is the only thing left to read. That is not a contrivance:
    labelFor() falls back to `name` and `id` exactly when a control has no
    accessible name, which is the case where the plain word is absent.
    """
    result = run_profile_fill(
        tmp_path,
        employment=_ONE_JOB,
        fields=[
            # Workday: only "datesection<part>" says which part this is.
            {"label": "workexperience-192--startdate-datesectionyear-input",
             "kind": "text"},
            {"label": "workexperience-192--startdate-datesectionmonth-input",
             "kind": "text"},
            # Oracle: only the "_<part>" suffix does.
            {"label": "-1_personprofilefields.rcf3214_year |"
                      " professional experience (1)* required.", "kind": "text"},
            {"label": "-1_personprofilefields.rcf3214_month |"
                      " professional experience (1)* required.", "kind": "text"},
        ],
    )
    assert [outcome for _, outcome in outcome_pairs(result)] == ["filled"] * 4
    assert list(result["values"].values()) == ["2018", "07", "2018", "07"]


def test_a_native_month_input_overrules_the_label_that_says_month(tmp_path):
    """`<input type="month">` holds "2018-07" and the browser rejects anything
    else. The label beside it says "month", and obeying the label would write
    "07" into a control that cannot hold it — this is the case where a control
    attribute has to beat label text, not merely be consulted alongside it."""
    result = run_profile_fill(
        tmp_path,
        employment=_ONE_JOB,
        fields=[{"label": _START_MONTH, "kind": "text", "type": "month"}],
    )
    assert outcome_for(result, _START_MONTH) == "filled"
    assert result["values"][_START_MONTH] == "2018-07"


def test_a_native_date_input_reports_missing_source(tmp_path):
    """`<input type="date">` needs "2018-07-01". A resume date has no day, so
    there is no honest value for it — and the browser would reject a partial
    one anyway. Reported, never guessed."""
    result = run_profile_fill(
        tmp_path,
        employment=_ONE_JOB,
        fields=[{"label": _START_MONTH, "kind": "text", "type": "date"}],
    )
    assert outcome_for(result, _START_MONTH) == "missing_source"
    assert result["values"][_START_MONTH] == ""


# ---------- 2. in what format ----------


def test_a_month_input_gets_two_digits_never_an_english_month_name(tmp_path):
    """The live defect this task was called on: Workday's month spinner was
    reported `filled` holding the string "March".

    Two digits rather than one: the widget renders MM and normalizes "3" to
    "03", and `sameIgnoringFormat` does not fold leading zeros — so writing "3"
    into a field that renormalizes would be reported `not_stuck`, a failure we
    invented ourselves.
    """
    result = run_profile_fill(
        tmp_path, employment=_ONE_JOB, fields=_workday_dates()
    )
    assert result["values"][_START_MONTH] == "07"
    assert result["values"][_END_MONTH] == "02"
    assert result["values"][_START_YEAR] == "2018"
    assert result["values"][_END_YEAR] == "2021"


@pytest.mark.parametrize(
    "options,expected",
    [
        # Oracle's actual list, quoted from the telemetry corpus.
        (["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], "Jul"),
        (["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"], "July"),
        (["01", "02", "03", "04", "05", "06",
          "07", "08", "09", "10", "11", "12"], "07"),
        (["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"], "7"),
    ],
)
def test_a_month_select_gets_whichever_rendering_its_own_options_use(
    tmp_path, options, expected
):
    """The option list is the ground truth for the format, not a house style.

    A month select is written by matching the profile month against the list,
    so the same answer lands as "Jul", "July", "07" or "7" depending on what
    the page offers. Guessing one form would be right on a quarter of pages.
    """
    result = run_profile_fill(
        tmp_path, employment=_ONE_JOB, fields=[_month_select(options)]
    )
    assert outcome_for(result, _START_MONTH) == "filled"
    assert result["values"][_START_MONTH] == expected


def test_a_month_select_offering_no_month_is_left_alone(tmp_path):
    """No fuzzy fallback for a date part.

    The generic option scorer takes anything reaching 40 of 100, and a
    two-digit month is a SUBSTRING of half the numbers a form offers: month
    "07" scores 57 against the year "2007" on containment alone. A month has
    twelve well-known renderings and all four forms of each are matched above;
    if none is on offer, this is not a month list. A near miss on an employment
    date is a date the user never gave us, not an approximation of one.
    """
    result = run_profile_fill(
        tmp_path,
        employment=_ONE_JOB,
        fields=[_month_select(["2005", "2006", "2007", "2008"])],
    )
    assert result["values"][_START_MONTH] == ""
    assert result["filled"] == []


# ---------- 3. whether we have it at all ----------


def test_a_day_control_reports_missing_source(tmp_path):
    """A day is unanswerable, so it is reported rather than invented.

    Nothing in either source carries one: the resume model is "Mon YYYY"
    (services/ats/resume_indexer.parse_month_year) and the autofill profile's
    education fields are `start_year`/`end_year`. Picking the 1st would state a
    start date the user never gave, on a record an employer may verify.

    `missing_source`, not `no_rule`: we know exactly what the control is and
    exactly which profile field would answer it, which is the difference
    between a coverage gap and a data gap — and Task 3 keeps only one of those
    in the failure rate.
    """
    result = run_fixture(tmp_path, "oracle_opaque_year")
    days = [
        (label, outcome) for label, outcome in outcome_pairs(result)
        if label.startswith("day |")
    ]
    assert [outcome for _, outcome in days] == ["missing_source", "missing_source"]
    assert [
        obs["rule_id"] for obs in result["observations"]
        if obs["label"].startswith("day |")
    ] == ["emp-day", "emp-day"]
    assert all(
        value == "" for label, value in result["values"].items()
        if label.startswith("day |")
    )


def test_a_day_the_source_does_carry_is_written(tmp_path):
    """The other side of it: `missing_source` on a day is a statement about the
    SOURCE, not a refusal to fill days. A hand-edited "2018-07-15" in the resume
    JSON carries one, and then both a day select and a native date control get
    it. Without this the day is unreachable code that happens to test green.
    """
    dated = [{**_ONE_JOB[0], "start_date": "2018-07-15", "end_date": "2021-02-20"}]
    icims = run_profile_fill(
        tmp_path,
        employment=dated,
        fields=[
            {"label": "day | icims_0_startdate_date | icims_0_startdate_date | day",
             "kind": "text"},
            {"label": "day | icims_0_enddate_date | icims_0_enddate_date | day",
             "kind": "text"},
            {"label": "Employment start date", "kind": "text", "type": "date"},
        ],
    )
    assert list(icims["values"].values()) == ["15", "20", "2018-07-15"]

    # Workday's day spinner named only by its id: "datesectionday" carries no
    # word boundary before "day", so it is the identifier form or nothing.
    workday_day = "workexperience-192--startdate-datesectionday-input"
    workday = run_profile_fill(
        tmp_path, employment=dated, fields=[{"label": workday_day, "kind": "text"}]
    )
    assert workday["values"][workday_day] == "15"


def test_a_year_only_source_reports_missing_source_for_the_month(tmp_path):
    """Having the date is not having every part of it.

    A hand-edited "2019" answers the year box beside it and answers nothing at
    all in the month box. Reporting the year `filled` and the month
    `missing_source` is the only description of that which is true of both.
    """
    result = run_profile_fill(
        tmp_path,
        employment=[{**_ONE_JOB[0], "start_date": "2019", "end_date": "2021"}],
        fields=_workday_dates(),
    )
    assert outcome_pairs(result) == [
        (_START_MONTH, "missing_source"),
        (_START_YEAR, "filled"),
        (_END_MONTH, "missing_source"),
        (_END_YEAR, "filled"),
    ]
    assert result["values"][_START_MONTH] == ""
    assert result["values"][_START_YEAR] == "2019"


def test_a_current_job_still_writes_nothing_into_its_end_parts(tmp_path):
    """Unchanged by the part writer, and easy to lose to it.

    A current job's To fields consume their list slot and emit nothing —
    neither a value nor an observation. Narrowing must not turn that into a
    `missing_source` report: the form is not missing an answer, the job has no
    end date, and reporting it would scale the gap metric with the FORM.

    Two entries because that is what makes it the SLOT path: with one current
    job and nothing else, `emp-end-month` has no value for any entry, so the
    rule is tagged missing_source in the table and reports before the slot is
    ever read. That is pre-existing and unrelated to narrowing — but it is what
    used to send the field on to `emp-end-date`, which wrote the literal word
    "Present" into a two-digit month spinner.
    """
    result = run_profile_fill(
        tmp_path,
        employment=[
            {**_ONE_JOB[0], "end_date": None, "current": True},
            {**_ONE_JOB[0], "start_date": "June 2015", "end_date": "June 2018"},
        ],
        fields=_workday_dates(),
    )
    assert outcome_pairs(result) == [
        (_START_MONTH, "filled"),
        (_START_YEAR, "filled"),
    ]
    assert result["values"][_END_MONTH] == ""
    assert result["values"][_END_YEAR] == ""


def test_present_is_never_narrowed_into_a_month_box(tmp_path):
    """The other live defect in the same widget, and the worse of the two.

    One current job leaves every employment end rule valueless, so matchRule
    scanned past them to `emp-end-date` — whose answer for a current job is the
    word "Present". That is what a Workday To-month spinner was being handed.
    """
    result = run_profile_fill(
        tmp_path,
        employment=[{**_ONE_JOB[0], "end_date": None, "current": True}],
        fields=_workday_dates(),
    )
    assert result["values"][_END_MONTH] == ""
    assert result["values"][_END_YEAR] == ""
    assert [obs["rule_id"] for obs in result["observations"]] == [
        "emp-start-month", "emp-start-year", "emp-end-month", "emp-end-year",
    ], "a whole-date rule claimed a part control"


# ---------- the whole date must not reach a part control ----------


def test_a_whole_date_is_never_written_into_a_part_control(tmp_path):
    """The eight live `not_stuck` observations, reproduced and fixed.

    With no month in the source, `emp-start-month` has nothing to give — and
    `matchRule` scans past a rule it cannot fill, which handed the month and
    year spinners to `emp-start-date` and wrote the whole string "spring 2018"
    into both. A rule holding a WHOLE date has to decline a control that asked
    for one part of one, whatever else can or cannot fill it.
    """
    result = run_profile_fill(
        tmp_path,
        employment=[{**_ONE_JOB[0], "start_date": "spring 2018",
                     "end_date": "whenever"}],
        fields=_workday_dates(),
    )
    assert outcome_pairs(result) == [
        (_START_MONTH, "missing_source"),
        (_START_YEAR, "missing_source"),
        (_END_MONTH, "missing_source"),
        (_END_YEAR, "missing_source"),
    ]
    assert set(result["values"].values()) == {""}


def test_a_free_text_date_field_still_gets_the_whole_date(tmp_path):
    """The other half of that guard: a box that wants a whole date still gets
    one, "Present" included. Blocking the part controls must not block these."""
    result = run_profile_fill(
        tmp_path,
        employment=[{**_ONE_JOB[0], "end_date": None, "current": True}],
        fields=[
            {"label": "Employment start date", "kind": "text"},
            {"label": "Employment end date", "kind": "text"},
        ],
    )
    assert result["values"]["Employment start date"] == "July 2018"
    assert result["values"]["Employment end date"] == "Present"


def test_a_whole_date_field_is_still_reformatted_for_a_native_control(tmp_path):
    """…and a whole-date box that is a NATIVE control is not exempt from the
    control-beats-everything rule. `<input type="month">` labelled "Employment
    start date" cannot hold "July 2018"; `<input type="date">` can hold nothing
    we have, because a resume date carries no day."""
    fields = [{"label": "Employment start date", "kind": "text", "type": t}
              for t in ("month", "date")]
    month, day = (
        run_profile_fill(tmp_path, employment=_ONE_JOB, fields=[field])
        for field in fields
    )
    assert month["values"]["Employment start date"] == "2018-07"
    assert outcome_for(month, "Employment start date") == "filled"
    assert day["values"]["Employment start date"] == ""
    assert outcome_for(day, "Employment start date") == "missing_source"


def test_the_availability_date_never_lands_in_an_employment_day_select(tmp_path):
    """iCIMS names its employment day select `icims_0_startdate_date`, which the
    `earliest-start-date` rule matches on "startdate". The user's availability
    date is not a day of a past job, and writing it there is silent and wrong.
    """
    label = "day | icims_0_startdate_date | icims_0_startdate_date | day"
    result = run_profile_fill(
        tmp_path,
        profile={"preferences": {"earliest_start_date": "2026-09-01"}},
        employment=_ONE_JOB,
        fields=[{"label": label, "kind": "text"}],
    )
    assert outcome_for(result, label) == "missing_source"
    assert result["values"][label] == ""


def test_an_employment_rule_still_cannot_reach_an_education_block(tmp_path):
    """The `not:` guard Task 7 verified, exercised where it is load-bearing.

    Two halves. The education YEAR boxes are now claimed by the education rules
    outright, so they no longer test the guard — they test that the education
    rules got there first, which is worth pinning on its own. A "Start Month"
    inside an education block is where the guard still does the work: there is
    no education month rule, `start.*month` matches, and without the guard the
    box would take an EMPLOYER's month — corrupting the field AND shifting
    every later employment entry by one.
    """
    education_month = {
        "label": "month | education-193--startdate-datesectionmonth-input | from",
        "kind": "text",
    }
    result = run_fixture(
        tmp_path,
        "workday_education_dates",
        employment=_ONE_JOB,
        fields=[*load_fixture("workday_education_dates")["fields"], education_month],
    )
    education_years = [
        (label, outcome) for label, outcome in outcome_pairs(result)
        if label.startswith("year |")
    ]
    assert [outcome for _, outcome in education_years] == ["filled", "filled"]
    assert result["values"][
        "year | education-193--firstyearattended-datesectionyear-input | from"
    ] == "2016", "an employment year reached an education block"
    assert outcome_for(result, education_month["label"]) == "no_rule"
    assert result["values"][education_month["label"]] == "", (
        "an employment month reached an education block"
    )


def test_a_graduation_month_never_receives_the_graduation_year(tmp_path):
    """The same guard on the education side, where the mismatch is loudest.

    "Graduation Month" and "Graduation Year" sit next to each other on plenty
    of forms, and `edu-end-year` matches "graduat" in BOTH. It has only a year
    to give, so the month box has to be declined rather than filled with it.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"education": [{"school": "State University", "end_year": "2018"}]},
        fields=[
            {"label": "Graduation Month", "kind": "text"},
            {"label": "Graduation Year", "kind": "text"},
        ],
    )
    assert outcome_for(result, "Graduation Month") == "no_rule"
    assert result["values"]["Graduation Month"] == ""
    assert result["values"]["Graduation Year"] == "2018"


def test_a_whole_date_rule_declines_a_part_control_even_when_alone(tmp_path):
    """The guard has to hold when NOTHING else can claim the field.

    labelFor() joins the enclosing legend into every control inside it, so a
    combined "Education & Work History" block puts both words on a date part.
    The education word holds `emp-start-month` off, and what is left are the two
    rules that carry a WHOLE date: `emp-start-date` (matched by "startdate …
    work") and `earliest-start-date` (matched by "startdate" alone). Either
    would write a whole date — one of them the user's availability, which is not
    a date on their employment history at all — into a two-digit month spinner.

    No plain "month" segment either, so the guard has to recognise the control
    from "datesectionmonth" alone.

    `no_rule` is the right answer: no rule for this shape yet, honestly logged.
    """
    label = "startdate-datesectionmonth-input | education & work history"
    result = run_profile_fill(
        tmp_path,
        profile={"preferences": {"earliest_start_date": "2026-09-01"}},
        employment=_ONE_JOB,
        fields=[{"label": label, "kind": "text"}],
    )
    assert outcome_for(result, label) == "no_rule"
    assert result["values"][label] == ""


# ---------- Oracle: DOM order is the only from/to signal there is ----------


def test_opaque_experience_dates_fill_from_then_to_in_dom_order(tmp_path):
    """Oracle's `rcf3214`/`rcf3215` differ only by a generated counter and share
    a container that names the BLOCK, not the field. No label parsing separates
    them, so the pair is resolved by DOM order: within a block every ATS renders
    From before To.

    Deliberately the LAST resort — the rule is guarded off every label that does
    name a start or an end, so a page carrying that signal never reaches it.
    """
    result = run_fixture(tmp_path, "oracle_opaque_year")
    values = result["values"]

    assert values[
        "-1_personprofilefields.rcf3214_year |"
        " -1_personprofilefields.rcf3214_year |"
        " professional experience (1)* required."
    ] == "2018"
    assert values[
        "-1_personprofilefields.rcf3215_year |"
        " -1_personprofilefields.rcf3215_year |"
        " professional experience (1)* required."
    ] == "2021"
    assert values[
        "month | -1_personprofilefields.rcf3214_month |"
        " -1_personprofilefields.rcf3214_month |"
        " professional experience (1)* required. | month"
    ] == "Jul"
    assert values[
        "month | -1_personprofilefields.rcf3215_month |"
        " -1_personprofilefields.rcf3215_month |"
        " professional experience (1)* required. | month"
    ] == "Feb"


def test_the_order_of_parts_inside_one_widget_does_not_matter(tmp_path):
    """The fixture guesses month-day-year within a single date widget, because
    telemetry stores no DOM order. That guess must not be load-bearing: each
    part is counted separately, so only the order of the WIDGETS matters."""
    fields = load_fixture("oracle_opaque_year")["fields"]
    shuffled = [fields[2], fields[0], fields[1], fields[5], fields[3], fields[4]]

    result = run_fixture(tmp_path, "oracle_opaque_year", fields=shuffled)
    assert result["values"][
        "-1_personprofilefields.rcf3214_year |"
        " -1_personprofilefields.rcf3214_year |"
        " professional experience (1)* required."
    ] == "2018"
    assert result["values"][
        "month | -1_personprofilefields.rcf3215_month |"
        " -1_personprofilefields.rcf3215_month |"
        " professional experience (1)* required. | month"
    ] == "Feb"


def test_a_label_that_names_its_end_of_the_range_never_uses_dom_order(tmp_path):
    """The guard that keeps the ordered fallback last.

    Workday's year boxes say "startdate"/"enddate" in their own identifier. The
    ordered rule hands out start,end,start,end — so if it could claim a label
    that names its own end of the range, a second block's From box would take
    the FIRST block's To year. The rule_id assertion is the test: on outcome
    alone both paths look identical for one block.
    """
    result = run_profile_fill(
        tmp_path, employment=_ONE_JOB, fields=_workday_dates()
    )
    assert [obs["rule_id"] for obs in result["observations"]] == [
        "emp-start-month", "emp-start-year", "emp-end-month", "emp-end-year",
    ]


# ---------- the date formats the two sources actually hold ----------


@pytest.mark.parametrize(
    "raw,year,month",
    [
        # The resume data model, and therefore the employment payload.
        ("July 2018", "2018", "07"),
        ("Jul 2018", "2018", "07"),
        ("Sept 2018", "2018", "09"),
        # Hand-edited settings/autofill.json and customized_json entries.
        ("2018-07", "2018", "07"),
        ("2018/07", "2018", "07"),
        ("2018-07-15", "2018", "07"),
        ("07/2018", "2018", "07"),
        ("2018", "2018", ""),
        # A range in a year box: "2018" is the year, and "20" is not a month.
        ("2018-2021", "2018", ""),
        ("", "", ""),
        ("whenever", "", ""),
    ],
)
def test_every_date_shape_the_two_sources_hold_is_parsed(
    tmp_path, raw, year, month
):
    """One table, because a parser that silently returns nothing is exactly how
    the whole date ended up in the month box: `emp-start-month` looked valueless
    for every real resume date, so `matchRule` scanned past it."""
    result = run_profile_fill(
        tmp_path,
        employment=[{**_ONE_JOB[0], "start_date": raw, "end_date": None,
                     "current": True}],
        fields=_workday_dates(),
    )
    assert result["values"][_START_YEAR] == year
    assert result["values"][_START_MONTH] == month
