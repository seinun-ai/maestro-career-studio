"""The two-part, time-scoped work-authorization question, in the extension.

A US application asks two things, and they are the only two an employer may
lawfully ask without running into citizenship-discrimination law:

  1. "Are you legally authorized to work in the United States?"
  2. "Will you now or in the future require sponsorship for employment visa
     status?"

An OPT holder answers YES to both — authorized today, sponsorship needed later.
One timeless `/sponsor/i` rule answered both the "now or in the future" knockout
and the "are you currently sponsored" variant with the same flag, so one of them
was always wrong. A wrong answer here fails the application silently and is not
recoverable, which is why an unknown must stay unknown (`missing_source`) rather
than be guessed from the other half.

The typed shape lives in `schemas/autofill_profile.py`; the backend's reader is
`autofill_profile.get_work_auth` and `test_autofill_profile_schema.py` pins it.
These tests pin the extension's own copy of that dual-read — the extension reads
the profile JSON directly, so the two are consistent by BEHAVIOUR, not by code.
"""

from tests.extension_harness import outcome_for, run_profile_fill

_AUTHORIZED = "Are you legally authorized to work in the United States?"
_FUTURE = (
    "Will you now or in the future require sponsorship for employment visa status?"
)
_NOW = "Do you currently require sponsorship?"


def _yes_no(label: str) -> dict:
    return {"label": label, "kind": "radio", "options": ["Yes", "No"]}


# ---------- the two questions answer independently ----------


def test_now_and_future_sponsorship_answer_independently(tmp_path):
    """The OPT case: no sponsorship now, sponsorship later. Both must be right."""
    result = run_profile_fill(
        tmp_path,
        profile={
            "work_auth": {
                "status": "opt",
                "authorized_now": True,
                "sponsorship_now": False,
                "sponsorship_future": True,
            }
        },
        fields=[_yes_no(_AUTHORIZED), _yes_no(_FUTURE), _yes_no(_NOW)],
    )
    assert result["values"] == {_AUTHORIZED: "Yes", _FUTURE: "Yes", _NOW: "No"}
    assert [outcome_for(result, label) for label in (_AUTHORIZED, _FUTURE, _NOW)] == [
        "filled",
        "filled",
        "filled",
    ]
    assert [o["rule_id"] for o in result["observations"]] == [
        "work-auth",
        "sponsorship-future",
        "sponsorship-now",
    ]


def test_the_now_or_future_knockout_is_answered_by_the_future_flag(tmp_path):
    """It READS present-tense and is not. Any future need means yes.

    Pinned on its own, with `now` the only half answered, because the failure is
    silent: routing this to the present-tense rule would answer "No" to the one
    question the employer actually screens on.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"sponsorship_now": False, "sponsorship_future": True}},
        fields=[_yes_no(_FUTURE)],
    )
    assert result["values"][_FUTURE] == "Yes"
    assert result["observations"][0]["rule_id"] == "sponsorship-future"


def test_a_bare_now_question_is_the_present_tense_one(tmp_path):
    """"now" without "or in the future" is a genuine present-tense question."""
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"sponsorship_now": False, "sponsorship_future": True}},
        fields=[_yes_no("Do you now require sponsorship?")],
    )
    assert result["values"]["Do you now require sponsorship?"] == "No"
    assert result["observations"][0]["rule_id"] == "sponsorship-now"


def test_two_sponsorship_fields_on_one_form_get_different_answers(tmp_path):
    """The split has to hold with both questions on the page at once.

    Doubles as the one fixture where a declared label is a substring of
    another, which pins the harness's composite-label attribution: a radio
    button reports "<option> | <question> | <group name>", and the shorter
    "Sponsorship" is contained in that too.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"sponsorship_now": False, "sponsorship_future": True}},
        fields=[{"label": "Sponsorship", "kind": "text"}, _yes_no(_NOW)],
    )
    # The catch-all takes the future answer; canonicalized, so a plain text
    # field gets "yes" rather than a stringified boolean.
    assert result["values"]["Sponsorship"] == "yes"
    assert result["values"][_NOW] == "No"
    assert outcome_for(result, "Sponsorship") == "filled"
    assert outcome_for(result, _NOW) == "filled"


def test_the_time_qualifier_must_come_from_the_same_label_source(tmp_path):
    """"currently" three label sources away does not make it a "now" question.

    labelFor joins up to eight sources with "|", and an ATS groups both
    sponsorship questions under one legend — so a plain work-authorization
    field inside that fieldset arrives as "...currently authorized... |
    Sponsorship". Letting the present-tense rule reach across the join would
    answer a work-authorization question with the sponsorship-now flag, which
    is the flag most likely to be unknown.

    That the broad rule then claims the field is a separate, pre-existing
    problem — a legend leaking into every label in its section is what
    block-scoped resolution is for; this test only pins that the split did not
    make it worse.
    """
    label = "Are you currently authorized to work? | Sponsorship"
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"sponsorship_now": False, "sponsorship_future": True}},
        fields=[{"label": label, "kind": "text"}],
    )
    assert result["observations"][0]["rule_id"] == "sponsorship-future"


def test_no_is_an_answer_and_never_reports_as_a_missing_one(tmp_path):
    """A citizen answers NO, and `false` must not read as "no value".

    The rule table tags a rule with no answer behind it `missing_source` on the
    truthiness of its value, so a real `false` is one step from being reported
    as an unanswered question — while the field it should have answered "No"
    stays blank.
    """
    result = run_profile_fill(
        tmp_path,
        profile={
            "work_auth": {
                "status": "citizen",
                "authorized_now": True,
                "sponsorship_now": False,
                "sponsorship_future": False,
            }
        },
        fields=[_yes_no(_FUTURE), _yes_no(_NOW)],
    )
    assert result["values"] == {_FUTURE: "No", _NOW: "No"}
    assert outcome_for(result, _FUTURE) == "filled"


def test_yes_no_strings_answer_the_same_way_booleans_do(tmp_path):
    """The Settings page writes its two selects as "yes"/"no" STRINGS.

    Both shapes reach the extension — the typed profile is booleans, a
    hand-edited or Settings-written one is strings — and the rules speak the
    same option keywords either way.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"authorized_now": "yes", "sponsorship_future": "no"}},
        fields=[_yes_no(_AUTHORIZED), _yes_no(_FUTURE)],
    )
    assert result["values"] == {_AUTHORIZED: "Yes", _FUTURE: "No"}


# ---------- an unknown answer stays unknown ----------


def test_unknown_now_reports_missing_source_rather_than_guessing(tmp_path):
    """A legacy profile cannot answer the "currently" variant. It must not try.

    `sponsorship_now` has no legacy source (SYSTEM.md §13
    `autofill-work-auth-shape`), and the broad sponsorship rule sitting below it
    CAN answer — matchRule keeps scanning past a valueless rule — so without a
    guard the future flag silently becomes the present-tense answer.
    """
    result = run_profile_fill(
        tmp_path,
        profile={
            "work_auth": {"authorized_to_work": True, "requires_sponsorship": True}
        },
        fields=[_yes_no(_NOW)],
    )
    assert outcome_for(result, _NOW) == "missing_source"
    assert result["observations"][0]["rule_id"] == "sponsorship-now"
    assert result["values"][_NOW] == "", "a question with no answer is never clicked"
    assert result["filled"] == []
    # The group query resolved, so the option texts rode along with the report.
    assert len(result["observations"][0]["options"]) == 2


def test_a_malformed_work_auth_answers_nothing_instead_of_crashing(tmp_path):
    """`work_auth` is hand-editable JSON and may not be an object at all.

    The same tolerance `get_work_auth` has: no answers, rather than an exception
    that takes down the whole fill — including the fields that had nothing to do
    with work authorization.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": "F-1 OPT", "personal": {"first_name": "Sample"}},
        fields=[_yes_no(_AUTHORIZED), {"label": "First Name", "kind": "text"}],
    )
    assert outcome_for(result, _AUTHORIZED) == "missing_source"
    assert result["values"][_AUTHORIZED] == ""
    assert result["values"]["First Name"] == "Sample"


# ---------- reading the pre-2026-07 two-boolean shape ----------


def test_the_legacy_shape_still_answers_both_questions_it_can(tmp_path):
    """Dual-read, not a rewrite: an older Settings page still POSTs this shape.

    The timeless legacy flag maps to the FUTURE half — the question employers
    gate on — never to the present-tense one.
    """
    result = run_profile_fill(
        tmp_path,
        profile={
            "work_auth": {"authorized_to_work": "yes", "requires_sponsorship": "yes"}
        },
        fields=[_yes_no(_AUTHORIZED), _yes_no(_FUTURE)],
    )
    assert result["values"] == {_AUTHORIZED: "Yes", _FUTURE: "Yes"}


def test_a_profile_holding_only_a_typed_key_is_not_read_as_legacy(tmp_path):
    """Shape detection is "carries ANY typed key", exactly as the backend's is.

    Detecting on one or two chosen keys would send a profile holding only
    `sponsorship_now` down the legacy branch, which reads neither typed key —
    discarding a knockout answer the user did supply, and reporting the field as
    unanswered.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"work_auth": {"sponsorship_now": False}},
        fields=[_yes_no(_NOW)],
    )
    assert result["values"][_NOW] == "No"
    assert outcome_for(result, _NOW) == "filled"
