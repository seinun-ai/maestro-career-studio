"""The one checkbox we are allowed to tick from a derivation.

`i currently work here | currentlyworkhere | workexperience-192--currentlyworkhere`
is on all three Workday work-experience blocks in the corpus, and nothing in the
resume answers it directly — it is DERIVED from the employment entry having no
end date. Hard rule HR-1 governs derivations: registered, and carrying
provenance, rather than inferred wherever it happens to be convenient. Here that
means a rule of its own (`emp-current`) carrying an explicit authorization flag,
so telemetry names the derivation and no later rule inherits permission to tick
boxes by growing a value.

Two properties from earlier tasks do most of the work in this file:

* **`click()` toggles.** A box the page already carries ticked is the user's own
  answer, and clicking it would clear the disclosure and then report it filled.
  That matters more here than it did for EEO: a ticked "I currently work here"
  on a job that ended in 2021 is a false statement on an employment record an
  employer can verify.
* **Blocks, not counters.** Which job the box belongs to comes from the block it
  sits in (Task 9), so the answer cannot drift away from the Job Title and
  Company beside it.

The default for every OTHER checkbox is untouched and stays `skipped_checkbox`.
"""

import pytest

from tests.extension_harness import outcome_for, outcome_pairs, run_profile_fill


# Verbatim from GET /api/autofill/telemetry/summary, with only the block index
# varied — bmo.wd3 reports block 192, directsupply.wd501 reports 101 and 126.
def _current_box(block: str, **flags) -> dict:
    return {
        "label": f"i currently work here | currentlyworkhere "
                 f"| workexperience-{block}--currentlyworkhere",
        "kind": "checkbox", **flags,
    }


def _employer_box(block: str) -> dict:
    return {"label": f"company* | companyname | workexperience-{block}--companyname",
            "kind": "text"}


# Exactly what /api/autofill/employment-blocks returns. `end_date` is None and
# `current` is true for the job in progress: the RESUME stores the literal
# string "Present" (it is one of the four distinct end_date values in the live
# base_resumes corpus), and `routers/autofill._employment_blocks` is what
# normalizes it — `current = not end or end.lower() in {present, current, now}`,
# with `end_date` blanked to None whenever that holds. So the extension never
# sees "Present" in `end_date`, and the derivation reads the flag that says so
# outright rather than re-deriving it, exactly as `empEndText`/`empEndDate`
# already do two lines above it.
_TWO_JOBS = [
    {"employer": "Northwind Traders", "title": "Senior Data Scientist",
     "location": "Austin, TX", "start_date": "March 2021", "end_date": None,
     "current": True, "description": "Built demand forecasting models."},
    {"employer": "Contoso Ltd", "title": "Data Scientist",
     "location": "Dallas, TX", "start_date": "July 2018",
     "end_date": "February 2021", "current": False,
     "description": "Shipped the experimentation platform."},
]


def _run(tmp_path, fields, employment=_TWO_JOBS):
    return run_profile_fill(tmp_path, fields=fields, employment=employment)


# ---------- the derivation ----------


def test_the_current_job_s_block_is_ticked_and_the_past_job_s_is_not(tmp_path):
    """The whole feature, and the half that matters is the second one.

    A wrongly ticked box on the 2021 job says the applicant still works there.
    That is not an approximation of the truth — it is a different, checkable
    claim, on the record an employer verifies first.
    """
    result = _run(tmp_path, [
        _employer_box("192"), _current_box("192"),
        _employer_box("214"), _current_box("214"),
    ])

    checked = result["checked"]
    assert checked[_current_box("192")["label"]] is True
    assert checked[_current_box("214")["label"]] is False
    # Same block, same job: the tick and the employer name beside it agree.
    assert result["values"][_employer_box("192")["label"]] == "Northwind Traders"


def test_the_derivation_is_registered_and_named_in_telemetry(tmp_path):
    """HR-1: a derived answer is a rule with an id, not an inference made at the
    write site. `emp-current` in the observation is what makes the derivation
    auditable — and what makes the past job's untouched box distinguishable from
    a checkbox nothing understood."""
    result = _run(tmp_path, [_current_box("192"), _current_box("214")])

    assert outcome_pairs(result) == [
        (_current_box("192")["label"], "filled"),
        # Recognised, derived to "no", deliberately left alone. Not `no_rule`,
        # which would say we did not know what the control was.
        (_current_box("214")["label"], "skipped_checkbox"),
    ]
    assert {o["rule_id"] for o in result["observations"]} == {"emp-current"}


def test_the_report_says_where_the_answer_came_from(tmp_path):
    """Provenance the user can check, not just provenance in the telemetry. The
    one thing they need to re-read is the end date on that job."""
    (item,) = _run(tmp_path, [_current_box("192")])["filled"]

    assert item["value"] == "ticked"
    assert "end date" in item["note"], item["note"]


def test_no_employment_payload_reports_its_gap(tmp_path):
    """Profile-only fill (no application and no base resume picked). We know
    exactly what the control is and have nothing to answer it with, which is
    `missing_source` — fixed by picking a resume, not by writing a rule."""
    result = _run(tmp_path, [_current_box("192")], employment=[])

    assert outcome_for(result, _current_box("192")["label"]) == "missing_source"
    assert result["checked"][_current_box("192")["label"]] is False


def test_a_block_past_the_end_of_the_resume_ticks_nothing(tmp_path):
    """Three rendered blocks, two jobs. The third has no entry behind it, so it
    is left exactly as the page rendered it — the same silence every other list
    rule keeps past the end of its list."""
    result = _run(tmp_path, [
        _current_box("192"), _current_box("214"), _current_box("300"),
    ])

    assert result["checked"][_current_box("300")["label"]] is False
    assert [label for label, _ in outcome_pairs(result)] == [
        _current_box("192")["label"], _current_box("214")["label"],
    ]


# ---------- click() toggles ----------


def test_a_box_the_page_already_ticked_is_left_alone(tmp_path):
    """click() TOGGLES, so a second click on the right answer is a wrong answer.

    A resumed application, or the user's own click before pressing Fill, arrives
    ticked. Clicking it would clear the box and then report it filled — the
    exact false success the EEO writer already guards against, on a field where
    being wrong is a false statement rather than an omission.
    """
    result = _run(tmp_path, [_current_box("192", checked=True)])

    assert result["checked"][_current_box("192")["label"]] is True
    assert "click" not in result["events"][_current_box("192")["label"]]
    assert result["filled"] == []


def test_a_click_the_page_cancels_is_reported_as_unregistered(tmp_path):
    """A framework that calls preventDefault() on the click cancels the state
    change: the event is dispatched and the box stays exactly as it was. The
    write has to be verified, not assumed, or the report claims a tick the user
    will not find."""
    result = _run(tmp_path, [_current_box("192", clickCancelled=True)])

    assert outcome_for(result, _current_box("192")["label"]) == "not_stuck"
    assert result["checked"][_current_box("192")["label"]] is False
    assert "manually" in result["filled"][0]["note"] or (
        "check the box" in result["filled"][0]["note"]
    ), result["filled"][0]["note"]


# ---------- the blast radius ----------


def test_the_generic_checkbox_default_is_unchanged(tmp_path):
    """Every other checkbox still reports `skipped_checkbox`, including one a
    rule matches and holds an answer for. Consent, subscribe and "I agree" boxes
    are not guessable from a profile, and this task adds ONE intent rather than
    a checkbox writer."""
    label = "i am willing to relocate | relocate_optin"
    result = run_profile_fill(
        tmp_path, fields=[{"label": label, "kind": "checkbox"}],
        profile={"preferences": {"willing_to_relocate": "yes"}},
    )

    assert outcome_for(result, label) == "skipped_checkbox"
    assert result["checked"][label] is False


def test_a_different_currently_work_question_is_not_this_derivation(tmp_path):
    """The live near miss, and the reason the pattern is not `/currently work/`.

    `yes | 42262[] | 42262_663244 | do you currently work for pwc
    (pricewaterhousecoopers)?` is a real Siemens checkbox asking whether the
    applicant works for the FIRM. No resume field answers it, and a looser
    pattern matches it — which would tick it for anyone whose most recent job is
    still in progress.

    It is no longer ANONYMOUS, and that is the only part of this that moved: it
    is the standing "have you previously been employed here" question, worded
    the way Siemens words it, so it reports `missing_source` against that rule
    instead of `no_rule`. The assertion that matters is unchanged and always
    was — the box is not ticked from the resume.
    """
    label = ("yes | 42262[] | 42262_663244 "
             "| do you currently work for pwc (pricewaterhousecoopers)?")
    result = _run(tmp_path, [{"label": label, "kind": "checkbox"}])

    assert outcome_for(result, label) == "missing_source"
    assert result["observations"][0]["rule_id"] == "previously-employed-here"
    assert result["checked"][label] is False


@pytest.mark.parametrize(
    "label",
    [
        # An employment block's other controls must not be swept in with it.
        "job title* | jobtitle | workexperience-192--jobtitle",
        "location | location | workexperience-192--location",
        # …nor the Siemens SELECT that asks the same question a different way.
        # It is answerable and this task deliberately does not answer it: the
        # brief scopes the allowlist to one checkbox intent, so this stays a
        # visible gap rather than a quiet generalization.
        "is current position? | 42343-8-0 | 42343-8-0 | is current position?",
    ],
)
def test_the_pattern_claims_only_the_box_it_was_written_for(tmp_path, label):
    result = _run(tmp_path, [{"label": label, "kind": "checkbox"}])

    assert result["checked"][label] is False
    assert "emp-current" not in {
        o["rule_id"] for o in result["observations"]
    }
