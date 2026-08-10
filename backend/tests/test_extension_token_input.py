"""The token input: one control that holds MANY values.

`type to add skills | search | skills--skills` is the same signature on both
Workday hosts in the corpus. It is a plain text box — telemetry recorded `kind:
text`, so `isCombobox()` returned false on the live page and the combobox writer
never ran — that converts whatever is typed into it into a chip when you press
Enter, and then EMPTIES ITSELF.

That last part is why this needs its own ladder rather than another call to
`commitValue`. `valueHolds` asks "is our value still there?", and for a token
input the answer to that is no on every successful write: the text became a
chip. Reading an empty box as success is equally wrong, because a controlled
input that rejects our write also ends up empty. So the commit is two-sided —
the text has to LAND first, and only then does the box clearing after Enter mean
a token was created.

Where the skills come from is the other half of this task, and it is asserted
here rather than assumed: they are the RESUME's skills, delivered by
`GET /api/autofill/skills` (see `test_autofill_router`). The autofill profile has
no `skills` key — live, its top-level keys are personal/education/work_auth/eeo/
preferences — and `test_the_profile_is_not_a_source_of_skills` pins that a
profile that grows one by hand is still not read.
"""

import pytest

from tests.extension_harness import outcome_for, run_profile_fill


# The live signature, verbatim from GET /api/autofill/telemetry/summary. Both
# `bmo.wd3` and `directsupply.wd501` report exactly this string.
_SKILLS_LABEL = "type to add skills | search | skills--skills"
_SKILLS_BOX = {"label": _SKILLS_LABEL, "kind": "text", "tokenizes": True}

# Enough to exceed the cap, and ordered so a test can say WHICH ones were
# dropped. Resume order is the priority order: the extension takes the first N.
_MANY = [f"Skill {i:02d}" for i in range(1, 15)]


def _run(tmp_path, *, fields=None, skills=None, profile=None):
    return run_profile_fill(
        tmp_path,
        fields=fields if fields is not None else [_SKILLS_BOX],
        skills=skills if skills is not None else ["Python", "SQL", "Airflow"],
        profile=profile,
    )


# ---------- the writer ----------


def test_each_skill_becomes_its_own_token(tmp_path):
    """One write plus one commit per skill, and the box ends up empty.

    The empty box is the POINT, not an accident: the widget consumed each value
    into a chip. A writer that dropped the whole list in at once would leave one
    chip reading "Python, SQL, Airflow", which is not a skill.
    """
    result = _run(tmp_path)

    assert outcome_for(result, _SKILLS_LABEL) == "filled"
    assert result["tokens"][_SKILLS_LABEL] == ["Python", "SQL", "Airflow"]
    assert result["values"][_SKILLS_LABEL] == ""


def test_the_commit_waits_for_the_text_to_land_before_pressing_enter(tmp_path):
    """The false success this ladder exists to kill.

    A controlled input that rejects our write clears itself on a later tick —
    and so does a token widget that accepted it. Both end empty, so a readback
    that only asked "is the box empty now?" would report `filled` for a field
    the user will find with no chips in it at all. The text has to survive the
    re-render FIRST; only then does clearing mean anything.

    No Enter is dispatched at all here, which is the observable half: we never
    ask the widget to commit text it has already thrown away.
    """
    result = _run(tmp_path, fields=[{**_SKILLS_BOX, "reverts": True}])

    assert outcome_for(result, _SKILLS_LABEL) == "not_stuck"
    assert result["tokens"][_SKILLS_LABEL] == []
    assert "keydown" not in result["events"][_SKILLS_LABEL]


def test_a_box_the_widget_re_renders_away_is_not_reported_filled(tmp_path):
    """A node swapped out mid-fill keeps whatever we assigned it forever —
    nothing is rendering it. That is caught before Enter rather than after: the
    box being gone tells us nothing about whether a chip exists (they are
    different nodes), but text that could not survive on the page is text the
    widget never had."""
    result = _run(tmp_path, fields=[{**_SKILLS_BOX, "detaches": True}])

    assert outcome_for(result, _SKILLS_LABEL) == "not_stuck"
    assert result["tokens"][_SKILLS_LABEL] == []


def test_a_box_that_never_tokenizes_is_reported_not_stuck_and_stops(tmp_path):
    """A box that keeps our text is a box that made no token.

    It also stops the run. The readback is bounded by a one-second timeout, so
    hammering a widget that is not a token input at all would spend ten seconds
    typing into it — and each failed attempt leaves the box holding text.

    And it stops the FRAME LOOP. This readback waits for a change that may never
    arrive, so the per-frame callback has to notice the timeout answered and
    stop re-arming; a version that only resolved the promise left a callback
    running forever and hung this test on the harness's subprocess timeout.
    """
    result = _run(tmp_path, fields=[{**_SKILLS_BOX, "tokenizes": False}])

    assert outcome_for(result, _SKILLS_LABEL) == "not_stuck"
    assert result["tokens"][_SKILLS_LABEL] == []
    assert result["events"][_SKILLS_LABEL].count("keydown") == 1, (
        "kept typing into a control that already refused the first token"
    )
    note = result["filled"][0]["note"]
    assert "manually" in note, note


def test_the_writer_neither_scrolls_the_page_nor_leaves_text_in_the_box(tmp_path):
    """focus() scrolls into view by default, and the search box of a token
    widget clears on blur. Both are the same decisions `commitValue` and
    `fillCombobox` already made; a second writer has to make them too."""
    events = _run(tmp_path)["events"][_SKILLS_LABEL]

    assert "focus:preventScroll" in events
    assert "focus" not in events, "focus() without preventScroll walks the page"
    assert "blur" in events, "left the widget focused with our text in it"


# ---------- the cap ----------


def test_the_cap_bounds_what_is_written(tmp_path):
    """A master resume carries 75 skills. Typing all of them into an
    application, one commit apiece, is neither wanted nor fast."""
    result = _run(tmp_path, skills=_MANY)

    assert result["tokens"][_SKILLS_LABEL] == _MANY[:10]


def test_the_report_says_how_many_skills_were_skipped(tmp_path):
    """A silent truncation reads as "we filled your skills" when it filled some.

    The count is what makes it actionable: the user cannot tell 10-of-14 from
    10-of-75 by looking at the chips, and the ones that matter for THIS
    application may be the ones that were dropped.
    """
    result = _run(tmp_path, skills=_MANY)

    (item,) = result["filled"]
    assert "10" in item["note"] and "14" in item["note"], item["note"]
    assert "4" in item["note"], item["note"]
    # The skills that landed are named, so "which ten" needs no guessing.
    assert item["value"].startswith("Skill 01, Skill 02")


def test_a_list_that_fits_under_the_cap_is_reported_without_a_hedge(tmp_path):
    """Hedging a success teaches the user to distrust the fills that worked —
    the same reasoning `filled_normalized` is reported bare."""
    (item,) = _run(tmp_path)["filled"]

    assert "note" not in item, item["note"]
    assert item["value"] == "Python, SQL, Airflow"


# ---------- which control, and which source ----------


def test_a_skills_control_that_cannot_hold_a_list_is_declined(tmp_path):
    """Siemens renders Skills as a multi-select over a fixed taxonomy
    (`skills | 42340[] | 42340 | skills`, 30 options). One select holds one
    option, so writing this answer there would state ONE skill for a person who
    supplied ten — the same reasoning that stops a multi-category race answer
    from being written into anything but per-option checkboxes.

    Recognised and declined, not silently ignored: `skip_rule` carries the rule
    id, so the telemetry says "this is a skills field we chose not to write",
    which is a different fix from "no rule matched it".
    """
    label = "skills | 42340[] | 42340 | skills"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "select",
                 "options": [{"value": "py", "textContent": "Python"},
                             {"value": "sql", "textContent": "SQL"}]}],
        skills=["Python", "SQL"],
    )

    assert outcome_for(result, label) == "skip_rule"
    assert result["values"][label] == ""
    assert result["filled"] == []


def test_a_label_that_only_mentions_skills_later_is_not_a_skills_box(tmp_path):
    """`42340-search__field | skills` is Siemens's search half of that same
    multi-select. labelFor() appends the fieldset legend and container text
    LAST, so a bare mention after the first `|` is the SECTION's name, not the
    field's — the same first-segment anchoring `emp-employer` and `emp-location`
    needed.

    It stays `no_rule` deliberately. `skip_rule` is neutral in the telemetry
    summary, and this control is a genuine coverage gap that should keep showing
    up as one until a writer can handle it.
    """
    label = "42340-search__field | skills"
    result = run_profile_fill(
        tmp_path, fields=[{"label": label, "kind": "combobox"}],
        skills=["Python", "SQL"],
    )

    assert outcome_for(result, label) == "no_rule"
    assert result["observations"][0]["rule_id"] is None


def test_a_skills_box_with_no_skills_behind_it_reports_its_gap(tmp_path):
    """No application and no base resume selected in the panel means no skills
    payload. Recognised-with-no-answer is `missing_source`, which is fixed by
    picking a resume — a different action from the one `no_rule` asks for."""
    result = _run(tmp_path, skills=[])

    assert outcome_for(result, _SKILLS_LABEL) == "missing_source"
    assert result["tokens"][_SKILLS_LABEL] == []


def test_the_profile_is_not_a_source_of_skills(tmp_path):
    """Skills come from the RESUME, and only from the resume.

    The autofill profile is an untyped dict, so a hand-edited `skills` key can
    exist; it is still not an authorized source. The resume's skills are the
    ones tailored to this application, and a second source would silently decide
    which of two answers an employer sees.
    """
    result = _run(
        tmp_path, skills=[],
        profile={"personal": {"first_name": "Sample"},
                 "skills": ["Invented", "By", "The Profile"]},
    )

    assert outcome_for(result, _SKILLS_LABEL) == "missing_source"
    assert result["tokens"][_SKILLS_LABEL] == []


@pytest.mark.parametrize(
    "label",
    [
        # The words appear, but never as this field's own name.
        "job title* | jobtitle | workexperience-192--jobtitle",
        "role description | workexperience-192--roledescription",
        "what skills would you like to develop? | q7",
    ],
)
def test_an_unrelated_field_is_not_handed_the_skill_list(tmp_path, label):
    """The last one is the interesting case: a free-text essay question that
    mentions skills is not a skills picker, and ten chips typed into it would be
    an answer nobody wrote."""
    result = run_profile_fill(
        tmp_path, fields=[{"label": label, "kind": "text", "tokenizes": True}],
        skills=["Python", "SQL"],
    )

    assert result["tokens"][label] == []
