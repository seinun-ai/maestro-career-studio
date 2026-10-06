"""The standing `consent_forms` permission, and what it unlocks.

The never-fill policy used to refuse agreement boxes outright, and then
signatures, initials, passwords and government identifiers at ANY setting. The
owner's decision (2026-09-26) is simpler: with the permission on, nothing is
refused by its label. It is the user's application and their consent, the
permission is explicit, recorded with a timestamp and a policy version, and
revocable, and the extension never moves to the next page or submits.

What did not change, and this file is mostly about it: the default is refusal.
Without the permission every list in `extension/shared/policy.js` still holds,
and an omitted argument is never the permission.
"""

import json
import shutil
import subprocess

import pytest

from tests.extension_harness import ROOT, outcome_for, run_profile_fill


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


_ONCE_REFUSED_AT_ANY_SETTING = [
    "signature* | applicant-signature",
    "please type your full name to sign | e-sign",
    "please type your initials to confirm | initials",
    "password | account--password",
    "social security number | ssn",
    "passport number | travel-doc",
    "driver's license number | dl-number",
    "what are your annual salary requirements | salary",
    "i willingly accept the terms and conditions | terms",
]


def _text_fill(tmp_path, label, consent):
    return run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text"}],
        profile={"personal": {"first_name": "Sample", "last_name": "Applicant"}},
        consent_forms=consent,
    )


@pytest.mark.parametrize("label", _ONCE_REFUSED_AT_ANY_SETTING)
def test_consent_unlocks_every_label(tmp_path, label):
    """With the permission on, no label is refused — not a signature, not a
    typed-name attestation, not a salary requirement. The engine still writes
    only what it has a fact for, so nothing here is invented: the point is that
    the refusal is gone, not that a value appears."""
    result = _text_fill(tmp_path, label, consent=True)
    assert outcome_for(result, label) != "policy_blocked"


@pytest.mark.parametrize("label", _ONCE_REFUSED_AT_ANY_SETTING)
def test_without_consent_the_same_labels_stay_refused(tmp_path, label):
    """The default did not move: without the permission every one of these is
    the policy's decision and nothing is written."""
    result = _text_fill(tmp_path, label, consent=False)
    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == ""


_POLICY_LABELS = [
    "Signature",
    "Please type your full name to sign",
    "Initials",
    "I willingly accept the Terms and Conditions",
    "What are your annual salary requirements",
    "Password",
    "Social Security Number",
    "What is your current salary?",
]


def _policy_verdicts(labels, calls):
    """`isPolicyBlocked` itself, straight from `shared/policy.js`, for each call
    shape in `calls` (a JSON literal for the second argument, or None to omit
    it)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    policy = (ROOT / "extension" / "shared" / "policy.js").read_text(encoding="utf-8")
    driver = (
        "globalThis.window = globalThis;\n" + policy + "\n"
        "const [labels, calls] = JSON.parse(process.argv[1]);\n"
        "const f = window.careerStudioCompanion.isPolicyBlocked;\n"
        "process.stdout.write(JSON.stringify(calls.map((c) => labels.map("
        "(l) => (c === null ? f(l) : f(l, c))))));\n"
    )
    out = subprocess.run([node, "-e", driver, json.dumps([labels, calls])],
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


def test_the_policy_refuses_no_label_once_consent_is_given():
    (on,) = _policy_verdicts(_POLICY_LABELS, [{"consentForms": True}])
    assert on == [False] * len(_POLICY_LABELS)


def test_the_policy_refuses_them_all_without_consent_or_when_it_is_omitted():
    """False, an empty options object and no argument at all are the same
    answer: an omitted argument is never the permission."""
    verdicts = _policy_verdicts(_POLICY_LABELS, [{"consentForms": False}, {}, None])
    assert verdicts == [[True] * len(_POLICY_LABELS)] * 3


def test_only_a_literal_true_is_the_permission():
    """A truthy stand-in (a string from a query parameter, a 1) is not consent."""
    verdicts = _policy_verdicts(["Signature"], [{"consentForms": "true"}, {"consentForms": 1}])
    assert verdicts == [[True], [True]]


def test_the_old_question_collector_never_receives_the_permission(tmp_path):
    """`collectOpenQuestions` (the old engine's AI path) calls the policy with
    no options, so it gets the default — refusal — whatever the setting says.
    The permission reaches the policy only through the callers that pass it:
    `fillFormFromProfile` and the fill loop's inventory.
    """
    from tests.extension_harness import rejection_reasons, run_open_questions

    result = run_open_questions(
        tmp_path,
        fields=[{"label": "I agree to the terms of service", "kind": "textarea"}],
    )
    assert rejection_reasons(result)["i agree to the terms of service"] == "policy_blocked"
