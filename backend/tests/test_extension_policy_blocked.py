"""Fields the engine recognises and deliberately never writes (HR-3).

Signatures, attestations, consent checkboxes and credentials are the one class
of field where declining IS the correct outcome. Scored as `no_rule` they were
a top-10 "failure" in live telemetry — `signature | icims_f_signature` alone
dragged one host to a 0.0% success rate — which pointed later work at writing
rules for controls no rule may ever fill.

So the deny-list is checked BEFORE the EEO opt-in, rule matching, and the
visibility gate: whether a signature field is written must be a policy
decision, not an accident of which regex happened to miss it.

The negative cases carry equal weight, and for a sharper reason than false
positives being annoying. `policy_blocked` is NEUTRAL — a field caught here
leaves the failure metric as well as the fill path, so an over-broad pattern
does not merely fail to fill "Middle Initial", it deletes the evidence that
nothing filled it. Every label in the not-blocked lists below is one an
ordinary applicant meets, and each sits a character away from a pattern.
"""

import re

import pytest

from tests.extension_harness import (
    ROOT,
    collected_labels,
    outcome_for,
    outcome_pairs,
    rejection_reasons,
    run_open_questions,
    run_profile_fill,
)


# A profile with real answers in it on purpose: the interesting failure is a
# signature field the rules COULD have filled, not one they had no answer for.
_PROFILE = {
    "personal": {
        "first_name": "Sample",
        "last_name": "Applicant",
        "email": "sample@example.test",
    }
}

_NEVER_FILL = [
    "Signature",
    "I certify the above is true and complete",
    "Create Password",
    "I agree to the Terms of Service",
]


@pytest.mark.parametrize(
    "label, expected_outcome, expected_value",
    [
        ("What is your current salary?", "policy_blocked", ""),
        ("Last drawn salary", "policy_blocked", ""),
        ("Current CTC", "policy_blocked", ""),
        ("Expected salary", "filled", "150000"),
        ("Salary", "policy_blocked", ""),
    ],
)
def test_salary_history_is_blocked_but_expectations_still_fill(
    tmp_path, label, expected_outcome, expected_value
):
    result = run_profile_fill(
        tmp_path,
        profile={"preferences": {"desired_salary": "150000"}},
        fields=[{"label": label, "kind": "text"}],
    )

    assert outcome_for(result, label) == expected_outcome
    assert result["values"][label] == expected_value


@pytest.mark.parametrize(
    "label",
    [
        "Electronic signature required for your salary expectations",
        "By entering your desired salary you accept the terms of service",
        "Target compensation and social security number",
        "I certify that your expected salary is accurate",
        "Create password for your desired salary",
    ],
)
def test_unconditional_policy_always_wins_over_salary_expectation_allowlist(
    tmp_path, label
):
    result = run_profile_fill(
        tmp_path,
        profile={"preferences": {"desired_salary": "150000"}},
        fields=[{"label": label, "kind": "text"}],
    )

    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == ""


def test_signature_and_consent_are_policy_blocked(tmp_path):
    """Never-fill fields must not be counted as coverage failures.

    These are HR-3 fields. The engine recognising them and declining IS the
    correct outcome, so they belong in their own bucket — not in no_rule, and
    emphatically not in the failure numerator.
    """
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[
            {"label": "Signature", "kind": "checkbox"},
            {"label": "I certify the above is true and complete", "kind": "checkbox"},
            {"label": "Create Password", "kind": "text"},
            {"label": "I agree to the Terms of Service", "kind": "checkbox"},
            {"label": "First Name", "kind": "text"},
        ],
    )

    assert outcome_pairs(result) == [
        ("Signature", "policy_blocked"),
        ("I certify the above is true and complete", "policy_blocked"),
        ("Create Password", "policy_blocked"),
        ("I agree to the Terms of Service", "policy_blocked"),
        ("First Name", "filled"),
    ]
    # Declining early must not cost the observation its identity: `by_kind`
    # buckets the summary on exactly this field, so a consent checkbox
    # reported as "text" moves the number under the wrong heading.
    assert [o["kind"] for o in result["observations"]] == [
        "checkbox",
        "checkbox",
        "text",
        "checkbox",
        "text",
    ]
    # The control still fills: a deny-list that quietly stops the whole loop
    # would satisfy the outcomes above.
    assert result["values"]["First Name"] == "Sample"
    assert [result["values"][label] for label in _NEVER_FILL] == ["", "", "", ""]
    # The panel's own "what did we fill" report has to agree with telemetry.
    assert [entry["label"] for entry in result["filled"]] == ["first name"]


@pytest.mark.parametrize(
    "label",
    [
        # Signing, in the wordings ATS forms actually use. "sign" needs both
        # boundaries and neither anchor: labelFor joins up to eight sources, so
        # the verb is almost never the first token of the label it builds.
        "Signature",
        "Sign and date below",
        "Please sign your name below",
        "Type your full name to sign",
        "eSign this document",
        "Initials",
        # Attestations. Each verb is listed separately because each is the only
        # thing standing between the user and a form they did not read — and
        # each is separated from the "I" by however much throat-clearing the
        # employer's lawyer preferred.
        "I certify the above is true and complete",
        "I hereby certify the information is correct",
        "I, the undersigned, certify the above",
        "I attest that the information is accurate",
        "I acknowledge receipt of the employee handbook",
        "I understand and agree to the above",
        "I have read and agree",
        "I do hereby consent to a background check",
        "I consent to a background check",
        # "consent" as a NOUN, which only the pronoun pattern can catch: the
        # bare-consent pattern below needs a "to"/"for" after it.
        "I give my consent",
        "I agree to be contacted about this role",
        "Consent to background check",
        "Certification that the details are correct",
        "Acknowledgement of receipt",
        "Attestation of accuracy",
        # A records release. Doubly dangerous: it also matches the `work-auth`
        # rule's /authoriz/, so before the deny-list a populated work
        # authorization answered a disclosure line yes.
        "Authorization for release of information",
        # Legal consent, where the checkbox IS the agreement.
        "Accept the Terms of Service",
        "Terms of Use",
        "Terms and Conditions",
        "Accept the Terms & Conditions",
        # Not "Privacy Policy acknowledgement": the attestation pattern catches
        # that one on the noun, which hid whether this alternative worked.
        "Accept the Privacy Policy",
        "Arbitration agreement",
        "Waiver of liability",
        "Release of liability",
        # Credentials.
        "Create Password",
        "Enter your passcode",
        # Government identifiers. Not credentials, but the same rule: the cost
        # of writing one into the wrong form is unbounded.
        "Social Security Number",
        "SSN",
        "National ID number",
        "Passport Number",
        "Driver's License Number",
        # ACCEPTED false positive, recorded rather than discovered later: \bsign\b
        # takes "sign-on" with it. One manual salary field is the price of
        # catching "Please sign here", and the asymmetry says pay it.
        "Expected sign-on bonus",
    ],
)
def test_every_never_fill_wording_is_blocked(tmp_path, label):
    """One case per alternative in the deny-list, so none of them is dead.

    An alternative no test reaches is indistinguishable from a typo'd one:
    both stay green when deleted, and both let the field through. The list is
    long on purpose — it is the vocabulary of the policy, not an example of it.
    """
    result = run_profile_fill(
        tmp_path, profile=_PROFILE, fields=[{"label": label, "kind": "text"}]
    )

    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == ""


@pytest.mark.parametrize(
    "label",
    [
        "Signature (type your full name)",
        "Please sign your name below",
        "Type your full name to sign",
    ],
)
def test_a_recognised_signature_field_is_not_written_by_the_rule_that_matches_it(
    tmp_path, label
):
    """The deny-list has to beat a rule that WOULD have filled the field.

    Every wording here is matched by the `full-name` rule, and the profile
    holds a name — so before the deny-list these controls were signed on the
    user's behalf. Three of them, because the first version of this test
    pinned one wording while two close cousins went on doing exactly that:
    "sign" was anchored to the start of the label, and a label is a join of
    up to eight sources, so the anchor almost never held.
    """
    result = run_profile_fill(
        tmp_path, profile=_PROFILE, fields=[{"label": label, "kind": "text"}]
    )

    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == "", "the extension signed for the user"
    assert result["filled"] == []
    # No rule_id: nothing matched, because nothing was asked to match.
    assert result["observations"][0]["rule_id"] is None


def test_a_policy_blocked_field_never_reports_missing_source(tmp_path):
    """Same label, empty profile — the rule that matches it has no value.

    Without the check running first this reports `missing_source`, whose whole
    meaning is "filling in your profile would fix this". It would not: adding a
    name to the profile still must not sign anything.
    """
    label = "Signature (type your full name)"
    result = run_profile_fill(
        tmp_path, profile={}, fields=[{"label": label, "kind": "text"}]
    )

    assert outcome_for(result, label) == "policy_blocked"


def test_a_hidden_signature_field_is_still_a_policy_decision(tmp_path):
    """Placement pin: the deny-list is evaluated before the visibility gate.

    Hidden fields are otherwise dropped from telemetry as clone junk. A
    never-fill field is a statement about the CONTROL, not about whether we
    could have reached it, and reporting it only when it happens to be visible
    would make the policy look like a rendering detail.
    """
    label = "Electronic signature"
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[{"label": label, "kind": "text", "hidden": True}],
    )

    assert outcome_for(result, label) == "policy_blocked"


@pytest.mark.parametrize("eeo_enabled", [False, True])
def test_an_eeo_field_that_is_also_a_signature_is_policy_blocked_either_way(
    tmp_path, eeo_enabled
):
    """Placement pin: the deny-list is evaluated before the EEO opt-in too.

    With the opt-in off this reported `eeo_disabled`, which reads as "turn the
    opt-in on and we will handle this". We never will — the answer for a
    signature does not depend on a user setting, and a bucket that flips with
    one is not reporting a policy.
    """
    label = "Disability self-identification signature"
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[{"label": label, "kind": "text"}],
        eeo_enabled=eeo_enabled,
    )

    assert outcome_for(result, label) == "policy_blocked"
    assert result["values"][label] == ""


@pytest.mark.parametrize(
    "label",
    [
        "Voluntary Self-Identification of Disability",
        "I identify as one or more of the classifications of a protected veteran",
        "I am not a protected veteran",
        "Yes, I have a disability, or have had one in the past",
        "I do not wish to answer (Gender)",
        "I decline to self-identify my race or ethnicity",
    ],
)
def test_eeo_self_identification_wording_survives_the_attestation_pattern(
    tmp_path, label
):
    """The boundary the attestation pattern is most likely to cross.

    EEO self-identification is written in the same first-person legalese as an
    attestation — "I identify as…", "I do not wish to answer" — and it is a
    whole opt-in feature with its own visibility rules and its own bucket.
    Swallowing it here would disable that feature silently, from the one place
    nobody would look. Run with the opt-in ON, where the loss would be real.
    """
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[{"label": label, "kind": "text"}],
        eeo_enabled=True,
    )

    assert outcome_for(result, label) != "policy_blocked"


def test_middle_initial_is_a_reportable_gap_and_not_a_blocked_field(tmp_path):
    """The exact shape of over-blocking this deny-list is most likely to cause.

    "Middle Initial"/"MI" is one of the most common fields on an ATS form and
    there is no rule for it, so `no_rule` is the CORRECT outcome: it is a real
    coverage gap, and the failure metric is how it gets prioritised. An
    /initial\\b/ pattern turns it neutral, and the gap disappears from
    top_failures without anyone deciding it should — the exact corruption this
    task exists to undo, running backwards.

    It is also a trap with a fuse on it: the queued profile expansion adds
    `middle_name`, and a rule for it could never fire, because the deny-list
    runs first.
    """
    result = run_profile_fill(
        tmp_path, profile=_PROFILE, fields=[{"label": "Middle Initial", "kind": "text"}]
    )

    assert outcome_for(result, "Middle Initial") == "no_rule"


def test_an_account_creation_legend_does_not_block_the_fields_under_it(tmp_path):
    """Why there is no /create.*account/ pattern.

    labelFor joins the fieldset legend and the container's label element into
    EVERY field's label, which is precisely how iCIMS/Taleo account-creation
    steps are built — so one such pattern blocks the name and email fields for
    the whole section. Bounding the `.*` does not help: the phrase arrives
    contiguous. And the only thing it uniquely caught was a username field,
    which cannot be pattern-matched safely either — "GitHub username" and
    "LinkedIn username" are fields we fill today.
    """
    fields = [
        {"label": "First Name | first_name | Create an Account", "kind": "text"},
        {"label": "Email | email | Create an Account", "kind": "text"},
    ]
    result = run_profile_fill(tmp_path, profile=_PROFILE, fields=fields)

    assert outcome_pairs(result) == [(field["label"], "filled") for field in fields]
    assert result["values"][fields[0]["label"]] == "Sample"
    assert result["values"][fields[1]["label"]] == "sample@example.test"


@pytest.mark.parametrize(
    "label",
    [
        # "certifications" is a section on half the ATS forms in existence, and
        # the singular is a field a profile expansion could plausibly fill —
        # which is why the attestation pattern demands "certif… THAT".
        "Licenses and Certifications",
        "Professional Certification",
        # All three contain "sign". Designation is a job-title field on non-US
        # ATS forms, and "reason for leaving" is one we want to keep visible.
        "Current Designation",
        "Design Portfolio URL",
        "Resignation reason",
        # A licence QUESTION is not a licence NUMBER.
        "Do you have a valid driver's license?",
        # The label text feeding the deny-list includes id/name fragments, so
        # substring-shaped patterns are checked against one here.
        "candidate_initialize_form",
        "Initial Start Date",
        # Ordinary fields whose wording brushes the consent patterns.
        "Terms of employment you are seeking",
        "What are your salary terms and expectations?",
        "GitHub username",
    ],
)
def test_ordinary_fields_are_not_policy_blocked(tmp_path, label):
    """False positives are not cheap: `policy_blocked` is neutral, so an
    over-broad pattern removes the field from the failure metric as well as
    from the fill path. The gap stops being filled AND stops being counted."""
    result = run_profile_fill(
        tmp_path, profile=_PROFILE, fields=[{"label": label, "kind": "text"}]
    )

    assert outcome_for(result, label) != "policy_blocked"


# ---------- the other write path: AI fill ----------
#
# There are two things on this page that can type into a field, and until now
# only one of them honoured the deny-list. collectOpenQuestions decides what is
# shown to the model at all, so it is where the AI path's policy has to live:
# a field it never collects is never tagged, and fillAnswersByQid addresses
# fields only through that tag.
#
# This path carries the LARGER risk of the two. The profile path writes a value
# the user typed into their own profile; this one writes free text a language
# model composed, into a field whose whole purpose is to record that the user
# agreed to something.


# The four wordings the review found reachable. Each is blocked in the profile
# path today and each was collected here — verified live: an iCIMS
# `wotc acknowledgement` SELECT sits in the observation corpus reaching the
# model right now, which is the select rendering below with a real host on it.
_AI_NEVER_FILL = [
    "Do you agree to the terms and conditions of this application?",
    "I certify that all information provided is true and complete",
    "I consent to a background check",
    "I acknowledge the arbitration agreement",
]

_ORDINARY = "Why do you want to work here?"


def _select(label, **extra):
    return {
        "label": label, "kind": "select",
        "options": [{"value": "Yes", "textContent": "Yes"},
                    {"value": "No", "textContent": "No"}],
        **extra,
    }


def _radio(label, **extra):
    """A grouped question the way an ATS renders one: the buttons read
    "Yes"/"No" and the question itself lives in the <legend> above them."""
    return {"label": label, "kind": "radio", "options": ["Yes", "No"],
            "legend": label, **extra}


@pytest.mark.parametrize("label", _AI_NEVER_FILL)
@pytest.mark.parametrize("kind", ["textarea", "select", "radio"])
def test_a_consent_field_is_never_offered_to_the_model(tmp_path, kind, label):
    """The deny-list has to hold in every rendering, not just free text.

    ATS forms render consent as a select or a radio pair far more often than as
    a text box, and those two renderings skipped the AI path's only content
    gate entirely: `QUESTIONY` is applied to plain text inputs alone, so a
    dropdown reached the model on the strength of having two options.
    """
    field = ({"label": label, "kind": "textarea"} if kind == "textarea"
             else _select(label) if kind == "select" else _radio(label))
    result = run_open_questions(tmp_path, fields=[field])

    assert collected_labels(result) == []
    # Not merely absent from the list: never made addressable. fillAnswersByQid
    # resolves a field through its data-rt-qid, so an untagged control cannot
    # be written even by an answer that arrives for some other question.
    assert result["qids"][label] == []
    assert rejection_reasons(result) == {label.lower(): "policy_blocked"}


@pytest.mark.parametrize("kind", ["textarea", "select", "radio", "text"])
def test_an_ordinary_screening_question_still_reaches_the_model(tmp_path, kind):
    """The cost of over-blocking here is a question the user answers by hand.

    Every rendering, because a deny-list check dropped into the wrong branch of
    the type ladder would keep three of them working and quietly kill the
    fourth — and the four branches are where the AI path's coverage lives.
    """
    field = (_select(_ORDINARY) if kind == "select"
             else _radio(_ORDINARY) if kind == "radio"
             else {"label": _ORDINARY, "kind": kind})
    result = run_open_questions(tmp_path, fields=[field])

    assert collected_labels(result) == [_ORDINARY.lower()]
    assert result["qids"][_ORDINARY] != []
    assert rejection_reasons(result) == {}


def test_a_consent_question_rendered_as_a_plain_text_input_is_blocked(tmp_path):
    """Placement pin: the policy gate runs BEFORE the question-ish gate.

    A consent line ending in "?" satisfies QUESTIONY, so on a text input the
    only thing between it and the model was `EXCLUDE`, which names no consent
    term at all. Leaning on QUESTIONY would also make the outcome depend on
    punctuation, and "I certify that…" has none.
    """
    label = _AI_NEVER_FILL[0]
    result = run_open_questions(
        tmp_path, fields=[{"label": label, "kind": "text"}])

    assert collected_labels(result) == []
    assert rejection_reasons(result) == {label.lower(): "policy_blocked"}


def test_a_radio_group_is_screened_on_its_legend_not_its_option_text(tmp_path):
    """The rendering the review named, and the one the option labels hide.

    A radio button's own label is "Yes" — it contains nothing to block. The
    consent is in the <legend> the group shares, which collectOpenQuestions
    re-derives precisely because the button's label is not the question. The
    re-derived label is the one that goes to the model, so it needs its own
    check; screening only the button text blocks nothing here.
    """
    legend = "I acknowledge the arbitration agreement"
    result = run_open_questions(
        tmp_path,
        fields=[{"label": "Arbitration", "kind": "radio",
                 "options": ["Yes", "No"], "legend": legend}],
    )

    assert collected_labels(result) == []
    assert result["qids"]["Arbitration"] == []
    assert rejection_reasons(result) == {legend.lower(): "policy_blocked"}


def test_a_field_both_gates_match_is_reported_as_the_policy_decision(tmp_path):
    """Ordering pin: the policy gate runs before EXCLUDE, not after it.

    "password" is in both lists, and which one answers first is the difference
    between "we decline to write this" and "the profile fill owns this field" —
    two different facts about a field nobody may ever fill. EXCLUDE is a
    routing list and gets narrowed whenever a rule moves between the paths;
    behind it, the policy would follow those edits around.
    """
    result = run_open_questions(
        tmp_path, fields=[{"label": "Create Password", "kind": "textarea"}])

    assert rejection_reasons(result) == {"create password": "policy_blocked"}


def test_a_consent_checkbox_is_not_collected_at_all(tmp_path):
    """Why the live consent CHECKBOXES are not part of this fix.

    `signature | icims_f_signature` and an "I have read and consent to the
    terms" tick box are both in the observation corpus, and neither ever
    reached the model: collectOpenQuestions walks selects, textareas, radios
    and text inputs, and a checkbox falls off the end of that ladder. Pinned
    with an ORDINARY checkbox — one that clears EXCLUDE and QUESTIONY both, so
    the ladder is the only thing turning it away. A consent checkbox would be
    caught by the deny-list as well and could not tell the two reasons apart;
    this is the boundary of what the deny-list is load-bearing for.
    """
    result = run_open_questions(
        tmp_path,
        fields=[{"label": "Would you like a recruiter to contact you?",
                 "kind": "checkbox"}],
    )

    assert collected_labels(result) == []
    assert rejection_reasons(result) == {}


def test_the_rejection_is_reported_and_carries_no_value(tmp_path):
    """A silent drop is a coverage gap nobody can see.

    `excluded` is the AI path's telemetry for what its gates turned away, and
    the point of a named reason is that "we declined on policy" and "we did not
    recognise this as a question" are different facts. It stays value-free like
    every other autofill signal: label, kind, reason and nothing else.
    """
    result = run_open_questions(
        tmp_path,
        fields=[_select("I consent to a background check"),
                {"label": _ORDINARY, "kind": "textarea"}],
    )

    assert result["collected"]["excluded"] == [{
        "label": "i consent to a background check",
        "kind": "select",
        "reason": "policy_blocked",
    }]
    assert collected_labels(result) == [_ORDINARY.lower()]


def test_both_copies_of_the_policy_deny_list_stay_identical():
    """The historical two-copy guard now pins one shared policy source.

    Both content-world writers consult the namespace function. The commit
    ladder is deliberately different: its two injected-context copies remain
    identity-pinned by test_both_copies_of_the_commit_ladder_stay_identical.
    """
    module = ROOT / "extension" / "content" / "policy.js"
    assert module.is_file(), "the shared policy module has not been created"
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "extension" / "content").glob("*.js"))
    )
    # The deny list is now TWO lists with different standing, and the split is
    # the point: NEVER_FILLED is absolute — signatures, passwords, government
    # identifiers — while CONSENT_FORMS is refused by default and unlocked by a
    # standing consent the user gives in Profile. Each must exist exactly once,
    # in this module, for the same reason the single list did.
    assert len(re.findall(r"const NEVER_FILLED = \[", sources)) == 1
    assert len(re.findall(r"const CONSENT_FORMS = \[", sources)) == 1
    policy = module.read_text(encoding="utf-8")
    assert "ns.isPolicyBlocked = isPolicyBlocked;" in policy
    assert "isPolicyBlocked(labelText" in sources
    # Consent DEFAULTS to absent: a caller that has not been taught about the
    # permission cannot unlock anything by omitting it.
    assert "{ consentForms = false } = {}" in policy


def test_a_password_input_is_declined_by_its_TYPE_not_its_label(tmp_path):
    """The deny-list reads label text; the type is the fact underneath it.

    A password box labelled in another language, or mislabelled with a phrase
    that a real rule matches, was protected only by no rule happening to fire on
    it. `isFormJunk` now excludes `type="password"` outright, so the label is the
    second gate rather than the only one. Nothing this extension fills is ever a
    password.

    The label here is deliberately one the email rule DOES match: before the
    type check, this field received the user's email address.
    """
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[
            {"label": "Email", "kind": "text", "type": "password"},
            {"label": "Email", "kind": "text"},
        ],
    )

    filled = [entry["value"] for entry in result["filled"]]
    assert filled == ["sample@example.test"], (
        "exactly one field should have been filled — the text one, never the "
        f"password input (got {filled})")
