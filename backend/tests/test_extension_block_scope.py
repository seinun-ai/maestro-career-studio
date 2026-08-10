"""Which resume entry a repeated form block gets, and why the leaf label cannot say.

A repeated block — Workday's `workexperience-192--…`, Siemens's `42343-2-0`,
iCIMS's "professional experience (1)" — renders the SAME field names once per
job. `location | location | workexperience-192--location` names a location;
nothing in it names *whose*. The enclosing block does, and the block's position
among the VISIBLE blocks is the entry number (HR-8).

What this replaces is a per-rule DOM-order counter (`rule._n`), which handed out
entries independently for every rule. That is not a theoretical drift: on
`directsupply.wd501.myworkdayjobs.com` block 126 renders no start-date inputs at
all, so `emp-start-month` never advanced for it and block 101 — whose Job Title
and Company came from the SECOND resume entry — received the FIRST entry's start
date. One rendered block, two different jobs, an end date before its own start.
`test_a_block_that_omits_a_field_no_longer_shifts_the_next_block` is that shape.

Three things a block-scoped scheme has to get right, one section each below:

1. **Which blocks count.** The hidden prototype block Workday and Siemens keep
   in the DOM is not a job, so it must consume no entry — and neither must a
   hidden `<select>` inside it, which the visibility gate deliberately lets
   through for select2-style widgets.
2. **Which entry each block gets.** Position among visible blocks OF THE SAME
   FAMILY: a page's education blocks number independently from its employment
   blocks, and a block past the end of the resume writes nothing.
3. **Which slot within a block.** The interleaved start,end lists that carry
   iCIMS's and Oracle's unlabelled From/To pairs are now indexed from the
   block's own base, so a block missing its To box cannot shift the next one.

The employer and location rules live here too. Both are what block scoping is
FOR — a Company or a Location field is meaningless until you know which job it
belongs to — and both were unfillable for a reason the block cannot fix on its
own, so the guards that keep them off everything else are argued here.
"""

import pytest

from tests.extension_harness import (
    outcome_for,
    outcome_pairs,
    run_profile_fill,
)


# Two jobs, most recent first, exactly as /api/autofill/employment-blocks
# returns them: "Mon YYYY" dates, `end_date` None while `current` is true, and
# `location` — the key Task 9 added to `routers/autofill._employment_blocks`
# (the resume model has always carried it; the payload dropped it).
_TWO_JOBS = [
    {
        "employer": "Northwind Traders",
        "title": "Senior Data Scientist",
        "location": "Austin, TX",
        "start_date": "March 2021",
        "end_date": None,
        "current": True,
        "description": "Built demand forecasting models.",
    },
    {
        "employer": "Contoso Ltd",
        "title": "Data Scientist",
        "location": "Dallas, TX",
        "start_date": "July 2018",
        "end_date": "February 2021",
        "current": False,
        "description": "Shipped the experimentation platform.",
    },
]


def _workday_block(block: str, *, dates: bool = True, **flags) -> list[dict]:
    """One Workday work-experience block's fields, in rendered order.

    `dates=False` is the live `directsupply` block 126: a block the applicant
    has not filled the dates into yet renders the text inputs and not the date
    widgets, which is precisely the case a per-rule counter cannot survive.
    """
    fields = [
        {"label": f"job title* | jobtitle | workexperience-{block}--jobtitle",
         "kind": "text", **flags},
        {"label": f"company* | companyname | workexperience-{block}--companyname",
         "kind": "text", **flags},
        {"label": f"location | location | workexperience-{block}--location",
         "kind": "text", **flags},
    ]
    if dates:
        fields += [
            {"label": f"month | workexperience-{block}--startdate-datesectionmonth-input | from*",
             "kind": "text", **flags},
            {"label": f"year | workexperience-{block}--startdate-datesectionyear-input | from*",
             "kind": "text", **flags},
            {"label": f"month | workexperience-{block}--enddate-datesectionmonth-input | to*",
             "kind": "text", **flags},
            {"label": f"year | workexperience-{block}--enddate-datesectionyear-input | to*",
             "kind": "text", **flags},
        ]
    return fields


def _run(tmp_path, fields, **kw):
    return run_profile_fill(
        tmp_path, fields=fields, employment=_TWO_JOBS, **kw
    )


# ---------- 1. which blocks count ----------


def test_a_hidden_prototype_block_consumes_no_entry(tmp_path):
    """The property Task 7 pinned and a block-ORDINAL scheme would break.

    Workday ships a pre-rendered template block in the DOM. It is not a job, so
    the first VISIBLE block is the first resume entry — not the second. Naming
    blocks 0/192/214 and handing entry N to block N would give the template the
    applicant's current job and shift every real block down one.
    """
    fields = (
        _workday_block("0", dates=False, hidden=True)
        + _workday_block("192", dates=False)
        + _workday_block("214", dates=False)
    )
    values = _run(tmp_path, fields)["values"]

    assert values["company* | companyname | workexperience-192--companyname"] == (
        "Northwind Traders")
    assert values["company* | companyname | workexperience-214--companyname"] == (
        "Contoso Ltd")
    assert values["company* | companyname | workexperience-0--companyname"] == ""


def test_a_hidden_select_in_the_prototype_block_consumes_no_entry(tmp_path):
    """The `!isSelect` hole in the visibility gate, closed by block scoping.

    `hidden` is `!isSelect && !isVisible(input)`, so a hidden NATIVE SELECT is
    never treated as hidden — deliberately, because select2-style widgets park
    theirs offscreen and we still want to fill them. The cost was that a hidden
    select inside the prototype block reached the list branch and took a slot.

    Block scoping makes the hole harmless where it did damage: the select is
    still reached, but the entry it resolves to is its BLOCK's, and a block no
    visible control belongs to has no entry at all.

    Both halves are asserted, because the old behaviour got both wrong. The
    template select was WRITTEN — Workday clones that block for every job the
    applicant adds next — and it took entry 0 while doing so, leaving the first
    block the applicant can actually see holding the second job.
    """
    fields = [
        {"label": "company* | companyname | workexperience-0--companyname",
         "kind": "select", "hidden": True,
         "options": [{"value": "n", "textContent": "Northwind Traders"},
                     {"value": "c", "textContent": "Contoso Ltd"}]},
        *_workday_block("192", dates=False),
    ]
    result = _run(tmp_path, fields)

    assert result["values"][
        "company* | companyname | workexperience-0--companyname"] == ""
    assert result["values"][
        "company* | companyname | workexperience-192--companyname"
    ] == "Northwind Traders"


def test_two_controls_for_one_field_in_a_block_get_the_same_job(tmp_path):
    """A select2/react-select field is TWO controls: the search box the user
    types into and the native `<select>` parked offscreen behind it. Both carry
    the field's name, so both match the same rule inside the same block.

    Counting matches within a block would give the second one the NEXT job's
    employer — the per-rule counter's failure reproduced one level down. A block
    resolves to one job, so every control in it reads that job.
    """
    fields = [
        {"label": "company* | companyname | workexperience-192--companyname",
         "kind": "text"},
        {"label": "company | companyname | workexperience-192--companyname | company",
         "kind": "select",
         "options": [{"value": "n", "textContent": "Northwind Traders"},
                     {"value": "c", "textContent": "Contoso Ltd"}]},
    ]
    values = _run(tmp_path, fields)["values"]

    assert values["company* | companyname | workexperience-192--companyname"] == (
        "Northwind Traders")
    assert values[
        "company | companyname | workexperience-192--companyname | company"] == "n"


def test_an_offscreen_select_still_fills_when_its_block_is_visible(tmp_path):
    """…and the other half: the select2 case the `!isSelect` term exists for.

    A native select parked offscreen inside a block whose other controls DO
    render belongs to a real job. Deciding block visibility per BLOCK rather
    than per control is what keeps this working while the test above passes —
    a scheme that simply refused hidden selects would break it.
    """
    fields = [
        *_workday_block("192", dates=False),
        {"label": "company* | companyname | workexperience-214--companyname",
         "kind": "select", "hidden": True,
         "options": [{"value": "c", "textContent": "Contoso Ltd"}]},
        {"label": "job title* | jobtitle | workexperience-214--jobtitle",
         "kind": "text"},
    ]
    result = _run(tmp_path, fields)

    assert result["values"][
        "company* | companyname | workexperience-214--companyname"
    ] == "c"
    assert outcome_for(
        result, "company* | companyname | workexperience-214--companyname"
    ) == "filled"


# ---------- 2. which entry each block gets ----------


def test_a_block_that_omits_a_field_no_longer_shifts_the_next_block(tmp_path):
    """The live `directsupply` corruption, in one assertion.

    Block 101 renders no date widgets. Under the per-rule counter that meant
    `emp-start-month` had never advanced when it reached block 126, so block
    126 — whose Job Title and Company are the SECOND job — was given the FIRST
    job's start date. The rendered block then read "Data Scientist, Contoso,
    March 2021 – February 2021": an end date before its own start.

    Every field of a block now resolves through the block, so they cannot
    disagree with each other.
    """
    fields = _workday_block("101", dates=False) + _workday_block("126")
    values = _run(tmp_path, fields)["values"]

    assert values["job title* | jobtitle | workexperience-126--jobtitle"] == (
        "Data Scientist")
    assert values[
        "month | workexperience-126--startdate-datesectionmonth-input | from*"
    ] == "07"
    assert values[
        "year | workexperience-126--startdate-datesectionyear-input | from*"
    ] == "2018"
    # The end date fills at all only because the block resolved to the job that
    # HAS one. Entry 0 is current, so under the old counter these emitted
    # nothing whatsoever.
    assert values[
        "month | workexperience-126--enddate-datesectionmonth-input | to*"
    ] == "02"
    assert values[
        "year | workexperience-126--enddate-datesectionyear-input | to*"
    ] == "2021"


def test_education_blocks_number_independently_of_employment_blocks(tmp_path):
    """Ordinals are per block FAMILY, not per page.

    Siemens numbers its sections `42343-…` (employment) and `42346-…`
    (education) and both repeat. Counting every block on the page in one
    sequence would give the first education block entry 2 because two
    employment blocks preceded it.
    """
    fields = [
        *_workday_block("192", dates=False),
        *_workday_block("214", dates=False),
        {"label": "school or university* | schoolname | education-193--schoolname",
         "kind": "text"},
    ]
    values = _run(
        tmp_path,
        fields,
        profile={"education": [
            {"school": "Northern Institute of Technology"},
            {"school": "Eastern State University"},
        ]},
    )["values"]

    assert values["school or university* | schoolname | education-193--schoolname"] == (
        "Northern Institute of Technology")


def test_a_block_past_the_end_of_the_resume_writes_nothing(tmp_path):
    """Three rendered blocks, two jobs. The third is not an error and not a
    gap in the sources — it is an empty block the applicant added — so it emits
    no observation, exactly as a consumed-empty slot did before."""
    fields = (
        _workday_block("192", dates=False)
        + _workday_block("214", dates=False)
        + _workday_block("240", dates=False)
    )
    result = _run(tmp_path, fields)

    assert result["values"][
        "company* | companyname | workexperience-240--companyname"] == ""
    assert not [
        label for label, _ in outcome_pairs(result)
        if "workexperience-240" in label
    ]


def test_a_page_with_no_repeated_blocks_still_fills_in_dom_order(tmp_path):
    """A flat form naming no block falls back to the DOM-order counter.

    Most ATS pages are this: two "Employer"/"Job Title" pairs and nothing that
    identifies either as a block. Block scoping adds a signal where one exists;
    it must not take away the only one there was.
    """
    fields = [
        {"label": "employer name", "kind": "text"},
        {"label": "job title", "kind": "text"},
        {"label": "employer name 2", "kind": "text"},
        {"label": "job title 2", "kind": "text"},
    ]
    values = _run(tmp_path, fields)["values"]

    assert values["employer name"] == "Northwind Traders"
    assert values["employer name 2"] == "Contoso Ltd"


def test_icims_numbers_its_repeated_blocks_in_the_control_id(tmp_path):
    """iCIMS puts the block index in the control id and nothing else — no
    section word, no container ordinal. `icims_0_startdate_month` and
    `icims_0_degree`/`icims_1_degree` are all live on charter.icims.com.

    Block 0 renders no year input here, so a per-rule counter reaches block 1's
    year having never advanced and hands it the FIRST job's year beside the
    SECOND job's month.
    """
    fields = [
        {"label": "month | icims_0_startdate_month | icims_0_startdate_month | month",
         "kind": "text"},
        {"label": "month | icims_1_startdate_month | icims_1_startdate_month | month",
         "kind": "text"},
        {"label": "year | icims_1_startdate_year | icims_1_startdate_year | year",
         "kind": "text"},
    ]
    values = _run(tmp_path, fields)["values"]

    assert values[
        "month | icims_0_startdate_month | icims_0_startdate_month | month"] == "03"
    assert values[
        "month | icims_1_startdate_month | icims_1_startdate_month | month"] == "07"
    assert values[
        "year | icims_1_startdate_year | icims_1_startdate_year | year"] == "2018"


def test_a_disabled_control_does_not_make_its_block_real(tmp_path):
    """The pre-pass has to skip exactly what the fill loop skips.

    A block awaiting an "Add" click renders its controls disabled. The loop has
    always ignored those, but a pre-pass that counted them would let such a
    block claim a job — and then the first block the applicant can actually type
    into would be filled with the SECOND job.
    """
    fields = [
        {"label": "company* | companyname | workexperience-0--companyname",
         "kind": "text", "disabled": True},
        *_workday_block("192", dates=False),
    ]
    values = _run(tmp_path, fields)["values"]

    assert values["company* | companyname | workexperience-192--companyname"] == (
        "Northwind Traders")
    assert values["company* | companyname | workexperience-0--companyname"] == ""


def test_siemens_numbered_blocks_resolve_per_block(tmp_path):
    """Siemens names blocks `<section>-<field>-<entry>` with a `-sample`
    prototype, and puts NOTHING else in the label — no vendor word, no section
    name. The `42343` section id is the only thing distinguishing an employment
    block from the education block beside it, which is why these labels cannot
    live in `fixtures/autofill/`: the corpus PII guard rejects any run of five
    or more digits, and the real section ids are five.

    Block 0 renders no Job Title, which is what makes this about the SECTION ID
    and not about DOM order: a per-rule counter reaches block 1's Job Title
    having never advanced, and hands it the first job's title beside the second
    job's employer.
    """
    fields = [
        {"label": "company | 42343-2-sample | 42343-2-sample | company",
         "kind": "text", "hidden": True},
        {"label": "company | 42343-2-0 | 42343-2-0 | company", "kind": "text"},
        {"label": "company | 42343-2-1 | 42343-2-1 | company", "kind": "text"},
        {"label": "job title | 42343-1-1 | 42343-1-1 | job title", "kind": "text"},
    ]
    values = _run(tmp_path, fields)["values"]

    assert values["company | 42343-2-0 | 42343-2-0 | company"] == "Northwind Traders"
    assert values["company | 42343-2-1 | 42343-2-1 | company"] == "Contoso Ltd"
    assert values["job title | 42343-1-1 | 42343-1-1 | job title"] == "Data Scientist"
    assert values["company | 42343-2-sample | 42343-2-sample | company"] == ""


# ---------- 3. which slot within a block ----------


_ICIMS_FROM = (
    "-1_personprofilefields.rcf3214_year | -1_personprofilefields.rcf3214_year "
    "| professional experience ({n})* required."
)
_ICIMS_TO = (
    "-1_personprofilefields.rcf3215_year | -1_personprofilefields.rcf3215_year "
    "| professional experience ({n})* required."
)


def test_an_unlabelled_from_to_pair_is_paired_within_its_own_block(tmp_path):
    """Task 8 deferred this, and it was the one assumption it could not test.

    iCIMS and Oracle name their experience date parts with a generated counter
    and put the only human text in the container, so nothing says which box is
    From and which is To. DOM order is the only signal, and the rule carries an
    interleaved start,end,start,end list read straight through — which works
    only if a From box is never rendered without its To beside it.

    Block 1 here renders a From and no To. Read straight through, block 2's
    From took slot 1 (the FIRST job's end date) and its To took slot 2 (the
    SECOND job's start) — every remaining box off by one, and a To showing a
    date earlier than the From above it. Indexing from the block's own base
    contains the damage to the block that caused it.
    """
    fields = [
        {"label": _ICIMS_FROM.format(n=1), "kind": "text"},
        {"label": _ICIMS_FROM.format(n=2), "kind": "text"},
        {"label": _ICIMS_TO.format(n=2), "kind": "text"},
    ]
    values = _run(tmp_path, fields)["values"]

    assert values[_ICIMS_FROM.format(n=1)] == "2021"
    assert values[_ICIMS_FROM.format(n=2)] == "2018"
    assert values[_ICIMS_TO.format(n=2)] == "2021"


def test_a_complete_from_to_pair_still_reads_from_before_to(tmp_path):
    """The positive control for the pairing above: within one block the first
    year box is still the From and the second still the To. Block scoping
    changes where each block STARTS reading, not the order inside it."""
    fields = [
        {"label": _ICIMS_FROM.format(n=1), "kind": "text"},
        {"label": _ICIMS_TO.format(n=1), "kind": "text"},
        {"label": _ICIMS_FROM.format(n=2), "kind": "text"},
        {"label": _ICIMS_TO.format(n=2), "kind": "text"},
    ]
    values = _run(tmp_path, fields)["values"]

    # Job 1 is current, so its To box has no answer and stays empty.
    assert values[_ICIMS_FROM.format(n=1)] == "2021"
    assert values[_ICIMS_TO.format(n=1)] == ""
    assert values[_ICIMS_FROM.format(n=2)] == "2018"
    assert values[_ICIMS_TO.format(n=2)] == "2021"


def test_every_block_s_day_select_still_reports_its_gap(tmp_path):
    """`emp-day` shares the interleaved list, so it needs the same block base.

    The rule exists to SAY a day is unanswerable — the resume model is
    "Mon YYYY" — and it does that by holding the whole date and reporting
    `missing_source` once the narrowing yields nothing. Read straight through,
    the second block's day select landed on slot 1, which is the FIRST job's end
    date: empty for a current job, and an empty slot is skipped in silence. The
    control that most needs to be reported then reported nothing at all.
    """
    day = (
        "day | -1_personprofilefields.rcf3214_date | "
        "-1_personprofilefields.rcf3214_date | professional experience ({n})* "
        "required. | day"
    )
    fields = [
        {"label": day.format(n=1), "kind": "select"},
        {"label": day.format(n=2), "kind": "select"},
    ]
    result = _run(tmp_path, fields)

    assert outcome_for(result, day.format(n=1)) == "missing_source"
    assert outcome_for(result, day.format(n=2)) == "missing_source"


# ---------- the employer rule ----------


def test_a_bare_company_label_fills_the_employer(tmp_path):
    """`emp-employer` wanted "employer" or "company NAME". Siemens labels the
    field "Company" and nothing else, so the single most important field of an
    employment block reported `no_rule` on the highest-volume host in the
    corpus."""
    fields = [{"label": "company | 42343-2-0 | 42343-2-0 | company", "kind": "text"}]
    result = _run(tmp_path, fields)

    assert outcome_for(result, "company | 42343-2-0 | 42343-2-0 | company") == "filled"
    assert result["values"]["company | 42343-2-0 | 42343-2-0 | company"] == (
        "Northwind Traders")


def test_the_workday_company_name_label_still_fills(tmp_path):
    """The label Workday actually emits — verbatim from telemetry, and already
    matched by `company\\s*name` through the `companyname` id segment. Pinned
    because widening the rule must not disturb the case that worked."""
    label = "company* | companyname | workexperience-192--companyname"
    result = _run(tmp_path, [{"label": label, "kind": "text"}])

    assert result["values"][label] == "Northwind Traders"


@pytest.mark.parametrize(
    "label",
    [
        # LIVE, on bmo.wd3.myworkdayjobs.com. A yes/no question whose text
        # happens to contain the word — the single strongest argument against
        # widening `emp-employer` to a bare /\bcompany\b/.
        "yes | candidateispreviousworker | uxz84 | have you worked with us "
        "before, including any company acquired by a financial group?*",
        # The container-text leakage class that produced POLICY_BLOCKED's
        # hardest case in Task 2: a legend lands in EVERY field of its section,
        # so a section headed "Company Information" would otherwise hand the
        # employer name to all of them.
        "job title* | jobtitle | workexperience-192--jobtitle | company information",
        # Fields that carry "company" first and are not the employer.
        "company website | companywebsite",
        "parent company | parentcompany",
        "company size | companysize",
    ],
)
def test_a_label_that_merely_mentions_a_company_is_not_the_employer(tmp_path, label):
    """Two independent guards, and both are load-bearing.

    The employer name must appear in the label's FIRST segment — its own
    label — because `labelFor()` appends the legend and container text last, so
    every leak lands after the first `|`. And the "Company <not-a-name>"
    compounds are excluded outright, because those DO name themselves first.
    """
    result = _run(tmp_path, [{"label": label, "kind": "text"}])

    assert result["values"][label] != "Northwind Traders"


# ---------- the location rule ----------


def test_an_employment_block_location_fills_from_that_block_s_job(tmp_path):
    """`location | location | workexperience-192--location` is verbatim
    telemetry, and reported `no_rule` for two separate reasons: no rule matched
    it, and the employment payload carried no location to write. Both halves
    had to be fixed for either to matter."""
    fields = _workday_block("192", dates=False) + _workday_block("214", dates=False)
    result = _run(tmp_path, fields)

    assert outcome_for(
        result, "location | location | workexperience-192--location") == "filled"
    assert result["values"][
        "location | location | workexperience-192--location"] == "Austin, TX"
    assert result["values"][
        "location | location | workexperience-214--location"] == "Dallas, TX"


@pytest.mark.parametrize(
    "label",
    [
        # All live. None of them is an employer's location, and each would be a
        # different kind of wrong answer.
        "preferred location | preferredlocations | preferredlocations-33",
        "location (city)* | candidate-location",
        "this full-time position is based on-site at the location listed. are "
        "you able and willing to work on-site at the location, including "
        "relocating if necessary?*",
        # Siemens's education block, whose location label is identical to its
        # employment block's except for the section id. The employment rule
        # declines rather than guess, so this stays unfilled — honestly.
        "location | 42346-9-0 | 42346-9-0 | location",
        # An education block under a legend that names both sections — the
        # leakage NOT_EDUCATION exists for, and the reason a school's campus
        # location is not a job's.
        "location | education-193--location | work experience and education",
        # An education block renders "Start Date" and "End Date" too, so the
        # section test for a NON-date rule must not accept a date word as proof
        # of an employment block. This is `EMP_BLOCK_NAME_RE` rather than
        # `EMP_SECTION_RE`.
        "location | 42346-9-0 | 42346-9-0 | location | start date",
        # Container text landing in a field that is not the Location box. It
        # sits after the first `|`, so the first-segment anchor declines it —
        # without that anchor the employer's city would be typed into a tick
        # box.
        "i currently work here | currentlyworkhere | "
        "workexperience-192--currentlyworkhere | location",
    ],
)
def test_a_location_outside_an_employment_block_is_not_a_job_location(tmp_path, label):
    """The rule is a conjunction: the label must name an employment section AND
    carry "location" in its own first segment. Neither signal is safe alone —
    "location" appears in a relocation question and in the applicant's own
    address, and an employment section name appears on every field of the
    block."""
    result = _run(tmp_path, [{"label": label, "kind": "text"}])

    assert result["values"][label] not in ("Austin, TX", "Dallas, TX")
