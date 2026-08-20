"""Rule-pass abstention: wrong scalar answers stay off option controls.

The fixtures are the three failures observed on a live Greenhouse application.
They run the real namespace-published form modules through ``loadModules()`` via
the shared harness: rule pass first, collection second, and essay routing last.
"""

import json

import pytest

from tests.extension_harness import collected_labels, run_open_questions


WORK_AUTH = (
    "Are you legally authorized to work in the country where you are applying "
    "for employment?"
)
HYBRID_NYC = (
    "This role is hybrid in New York City. Are you willing and able to work "
    "there at least 2 days per week?"
)
STARTUP_ESSAY = (
    "If you have startup experience, tell us more about it, including company "
    "stage, team size…"
)


def _yes_no(label: str) -> dict:
    return {
        "label": label,
        "kind": "select",
        "options": [
            {"value": "yes", "textContent": "Yes"},
            {"value": "no", "textContent": "No"},
        ],
    }


def _labels(rows: list[dict]) -> list[str]:
    return [row["label"] for row in rows]


def test_work_authorization_beats_the_country_rule(tmp_path):
    result = run_open_questions(
        tmp_path,
        fields=[_yes_no(WORK_AUTH)],
        profile={
            "personal": {"country": "United States"},
            "work_auth": {"authorized_now": True},
        },
    )

    assert result["values"][WORK_AUTH] == "yes"
    assert "United States" not in json.dumps(result["values"])
    assert result["collected"]["questions"] == []
    assert result["collected"]["retryables"] == []


@pytest.mark.parametrize(
    "label",
    [
        WORK_AUTH,
        "Are you legally authorized to work in this country?",
        "Are you authorized to work in the United States?",
        "Are you authorized to work in the U.S. without sponsorship?",
        "Will you require sponsorship for an employment visa status?",
    ],
)
def test_unknown_work_authorization_is_released_value_free(tmp_path, label):
    result = run_open_questions(
        tmp_path,
        fields=[_yes_no(label)],
        profile={},
    )

    assert result["values"][label] == ""
    assert collected_labels(result) == [label.lower()]
    assert result["collected"]["retryables"] == []
    assert "known_value" not in result["collected"]["questions"][0]


def test_missing_source_release_is_limited_to_opted_in_rules(tmp_path):
    """Removing the per-rule flag must not expose every typed profile field."""
    label = "Country of citizenship?"
    result = run_open_questions(
        tmp_path,
        fields=[{"label": label, "kind": "select", "options": [
            {"value": "us", "textContent": "United States"},
            {"value": "ca", "textContent": "Canada"},
        ]}],
        profile={},
    )

    assert collected_labels(result) == []
    assert result["collected"]["retryables"] == []
    assert result["collected"]["excluded"] == [{
        "label": label.lower(),
        "kind": "select",
        "reason": "excluded",
    }]


def test_a_released_select2_input_keeps_combobox_kind(tmp_path):
    label = "Country of citizenship?"
    result = run_open_questions(
        tmp_path,
        fields=[{"label": label, "kind": "text", "select2Ancestor": True}],
        harness={"released_labels": [label]},
    )

    [question] = result["collected"]["questions"]
    assert question["kind"] == "combobox"
    assert "known_value" not in question


def test_hybrid_location_question_is_released_instead_of_filled_with_city(tmp_path):
    result = run_open_questions(
        tmp_path,
        fields=[_yes_no(HYBRID_NYC)],
        profile={"personal": {"city": "Liberty Hill"}},
    )

    assert result["values"][HYBRID_NYC] == ""
    assert collected_labels(result) == [HYBRID_NYC.lower()]
    assert result["collected"]["retryables"] == []
    assert "Liberty Hill" not in json.dumps(result["routed"])


def test_startup_essay_never_takes_the_employer_scalar(tmp_path):
    result = run_open_questions(
        tmp_path,
        fields=[{"label": STARTUP_ESSAY, "kind": "textarea"}],
        profile={},
        harness={"employment": [{"employer": "Seinun LLC"}]},
    )

    assert result["values"][STARTUP_ESSAY] == ""
    assert _labels(result["routed"]["essays"]) == [STARTUP_ESSAY.lower()]
    assert result["routed"]["chooseFields"] == []


def test_questiony_textarea_never_takes_any_scalar_rule(tmp_path):
    """Pin the structural guard independently of the employer `not:` guard."""
    label = "Tell us more about your GitHub experience"
    result = run_open_questions(
        tmp_path,
        fields=[{"label": label, "kind": "textarea"}],
        profile={"personal": {"github": "https://github.com/sample"}},
    )

    assert result["values"][label] == ""
    assert _labels(result["routed"]["essays"]) == [label.lower()]


@pytest.mark.parametrize(
    "field",
    [
        {
            "label": "Country of citizenship?",
            "kind": "select",
            "options": [
                {"value": "remote", "textContent": "Remote"},
                {"value": "onsite", "textContent": "On-site"},
            ],
        },
        {
            "label": "Country of citizenship?",
            "kind": "listboxButton",
            "listbox": ["Remote", "On-site"],
        },
        {
            "label": "Country of citizenship?",
            "kind": "combobox",
            "listbox": ["Remote", "On-site"],
        },
        {
            "label": "Country of citizenship?",
            "kind": "radio",
            "legend": "Country of citizenship?",
            "options": ["Remote", "On-site"],
        },
    ],
    ids=["select", "listbox-button", "combobox", "radio-group"],
)
def test_option_mismatch_releases_every_option_control_without_a_retry(
    tmp_path, field
):
    label = field["label"]
    result = run_open_questions(
        tmp_path,
        fields=[field],
        profile={"personal": {"country": "United States"}},
    )

    assert result["values"][label] in ("", "Select One")
    assert collected_labels(result) == [label.lower()]
    assert result["collected"]["retryables"] == []
    [question] = result["collected"]["questions"]
    assert "known_value" not in question
    assert "United States" not in json.dumps(result["routed"])


def test_github_url_rule_still_fills(tmp_path):
    label = "GitHub URL"
    result = run_open_questions(
        tmp_path,
        fields=[{"label": label, "kind": "text"}],
        profile={"personal": {"github": "https://github.com/sample"}},
    )

    assert result["values"][label] == "https://github.com/sample"
    assert result["collected"]["questions"] == []
    assert result["collected"]["retryables"] == []


def test_policy_blocked_beats_even_an_explicit_release(tmp_path):
    label = "I consent to a background check"
    result = run_open_questions(
        tmp_path,
        fields=[_yes_no(label)],
        harness={"released_labels": [label]},
    )

    assert collected_labels(result) == []
    assert result["collected"]["retryables"] == []
    assert result["collected"]["excluded"] == [{
        "label": label.lower(),
        "kind": "select",
        "reason": "policy_blocked",
    }]


def test_eeo_option_miss_is_retryable_and_never_released(tmp_path):
    label = "Gender"
    result = run_open_questions(
        tmp_path,
        fields=[{
            "label": label,
            "kind": "select",
            "options": [
                {"value": "male", "textContent": "Male"},
                {"value": "nonbinary", "textContent": "Nonbinary"},
            ],
        }],
        profile={"eeo": {"gender": "female"}},
        harness={"eeo_enabled": True},
    )

    assert collected_labels(result) == []
    [retryable] = result["collected"]["retryables"]
    assert retryable["label"] == label.lower()
    assert retryable["known_value"] == "female"
