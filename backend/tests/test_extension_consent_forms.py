"""Standing consent for an application's own agreement boxes.

The never-fill policy used to refuse these outright. It no longer does, and the
reason is not that the wording turned out to be harmless: it is the user's
application and their consent, the card never submits anything, and the
permission is now explicit, recorded with a timestamp and a policy version, and
revocable. What changed is that there IS a permission to point at.

Two things did not change, and this file is mostly about them: what stays
refused at any setting, and the fact that the default is refusal.
"""

import pytest

from tests.extension_harness import outcome_for, run_profile_fill


_TERMS = "yes, i have read and consent to the terms and conditions* | termsandconditions--accepttermsandagreements"


def _run(tmp_path, label, consent, checked=False):
    return run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "checkbox", "checked": checked}],
        profile={"personal": {"first_name": "Sample"}},
        consent_forms=consent,
    )


def test_the_terms_box_is_refused_until_consent_is_given(tmp_path):
    """The default, and it is the absence of a permission rather than a
    judgement about the field."""
    result = _run(tmp_path, _TERMS, consent=False)
    assert outcome_for(result, _TERMS) == "policy_blocked"
    assert result["checked"][_TERMS] is False


def test_the_terms_box_is_ticked_once_consent_is_given(tmp_path):
    result = _run(tmp_path, _TERMS, consent=True)
    assert outcome_for(result, _TERMS) == "filled"
    assert result["checked"][_TERMS] is True


def test_a_box_that_arrives_ticked_is_never_clicked_again(tmp_path):
    """click() toggles, so a box already carrying the answer must be left
    alone — the same rule every other checkbox in this engine follows."""
    result = _run(tmp_path, _TERMS, consent=True, checked=True)
    assert result["checked"][_TERMS] is True
    assert result["already"] == [{"label": _TERMS[:60], "value": "ticked"}]


def test_a_click_the_page_cancelled_is_not_reported_as_agreed(tmp_path):
    """An agreement the form did not register must never be reported as made."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": _TERMS, "kind": "checkbox", "clickCancelled": True}],
        profile={}, consent_forms=True,
    )
    assert outcome_for(result, _TERMS) == "not_stuck"
    assert result["checked"][_TERMS] is False


@pytest.mark.parametrize("label", [
    "signature* | applicant-signature",
    "please type your initials to confirm | initials",
    "password | account--password",
    "social security number | ssn",
    "passport number | travel-doc",
    "driver's license number | dl-number",
])
def test_what_no_consent_can_unlock(tmp_path, label):
    """The line that did not move, and why it is a different line.

    A signature or a set of initials is an ACT rather than an agreement — the
    field asks you to produce your name, and producing it for you is not the
    same as ticking a box you were going to tick anyway. Passwords and
    government identifiers are not consent at all; they are credentials, and no
    setting in a profile makes it right to type one into a page on someone
    else's behalf.
    """
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text"}],
        profile={"personal": {"first_name": "Sample", "last_name": "Applicant"}},
        consent_forms=True,
    )
    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == ""


def test_consent_does_not_reach_the_ai_path(tmp_path):
    """The model still never sees these.

    Consent authorizes THIS engine to tick a box the user decided to tick. It
    is not a licence for a model to decide what to agree to, so the question
    collector's gate is unchanged and a consent field is never even offered.
    """
    from tests.extension_harness import rejection_reasons, run_open_questions

    result = run_open_questions(
        tmp_path,
        fields=[{"label": "I agree to the terms of service", "kind": "textarea"}],
    )
    assert rejection_reasons(result)["i agree to the terms of service"] == "policy_blocked"
