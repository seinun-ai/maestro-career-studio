"""Value-directed and sequenced writes for Guided Apply's second pass."""

from tests.extension_harness import run_guided_write


def test_listbox_matches_the_model_answer(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-country",
            "label": "Country",
            "kind": "listboxButton",
            "listbox": ["United States", "Canada"],
        }],
        items=[{
            "qid": "q-country",
            "kind": "combobox",
            "answer": "Canada",
        }],
    )

    assert result["results"] == [{"qid": "q-country", "outcome": "filled"}]
    assert result["values"]["Country"] == "Canada"


def test_listbox_recovers_with_the_known_value(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-country",
            "label": "Country",
            "kind": "listboxButton",
            "listbox": ["US", "Canada"],
        }],
        items=[{
            "qid": "q-country",
            "kind": "combobox",
            "answer": "United States",
            "knownValue": "US",
        }],
    )

    assert result["results"] == [
        {"qid": "q-country", "outcome": "match_recovered"}
    ]
    assert result["values"]["Country"] == "US"


def test_listbox_no_match_leaves_the_field_untouched(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-country",
            "label": "Country",
            "kind": "listboxButton",
            "listbox": ["Andorra", "Bhutan"],
        }],
        items=[{
            "qid": "q-country",
            "kind": "combobox",
            "answer": "Canada",
        }],
    )

    assert result["results"] == [{"qid": "q-country", "outcome": "not_stuck"}]
    assert result["values"]["Country"] == "Select One"


def test_typeahead_uses_the_native_setter_before_matching(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-country",
            "label": "Country",
            "kind": "combobox",
            "trackedValue": True,
            "listbox": ["Canada", "Mexico"],
        }],
        items=[{"qid": "q-country", "kind": "combobox", "answer": "Canada"}],
    )

    assert result["results"] == [{"qid": "q-country", "outcome": "filled"}]
    assert result["values"]["Country"] == "Canada"
    assert "tracked-set" not in result["events"]["Country"]


def _first_event_index(order, label):
    """Where in the event log this control was first touched."""
    return next(i for i, event in enumerate(order)
                if event.startswith(f"{label}:"))


def test_mixed_kinds_write_in_input_order_and_return_every_qid_once(tmp_path):
    fields = [
        {"qid": "q-text", "label": "Notice", "kind": "text"},
        {
            "qid": "q-select",
            "label": "Shift",
            "kind": "select",
            "options": [
                {"value": "day", "textContent": "Day"},
                {"value": "night", "textContent": "Night"},
            ],
        },
        {
            "qid": "q-radio",
            "label": "Eligible?",
            "legend": "Eligible?",
            "kind": "radio",
            "options": ["Yes", "No"],
        },
        {"qid": "q-check", "label": "Remote", "kind": "checkbox"},
    ]
    items = [
        {"qid": "q-text", "kind": "text", "answer": "Two weeks"},
        {"qid": "q-select", "kind": "select", "answer": "Night"},
        {"qid": "q-radio", "kind": "radio", "answer": "Yes"},
        {"qid": "q-check", "kind": "checkbox", "answer": "Yes"},
    ]

    result = run_guided_write(tmp_path, fields=fields, items=items)

    assert result["results"] == [
        {"qid": "q-text", "outcome": "filled"},
        {"qid": "q-select", "outcome": "filled"},
        {"qid": "q-radio", "outcome": "filled"},
        {"qid": "q-check", "outcome": "filled"},
    ]
    assert result["values"]["Notice"] == "Two weeks"
    assert result["values"]["Shift"] == "night"
    assert result["values"]["Eligible?"] == "Yes"
    assert result["checked"]["Remote"] is True
    first_event = [
        _first_event_index(result["order"], label)
        for label in ["Notice", "Shift", "Yes", "Remote"]
    ]
    assert first_event == sorted(first_event)


def test_a_chip_rerender_does_not_lose_the_next_item(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[
            {
                "qid": "q-skill",
                "label": "Skill",
                "kind": "combobox",
                "listbox": ["Python"],
            },
            {"qid": "q-city", "label": "City", "kind": "text"},
        ],
        items=[
            {"qid": "q-skill", "kind": "combobox", "answer": "Python"},
            {"qid": "q-city", "kind": "text", "answer": "Austin"},
        ],
        rerender_after_option={"sourceQid": "q-skill", "targetQid": "q-city"},
    )

    assert result["results"] == [
        {"qid": "q-skill", "outcome": "filled"},
        {"qid": "q-city", "outcome": "filled"},
    ]
    assert result["values"]["City"] == "Austin"


def test_a_missing_element_still_returns_its_input_qid(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[],
        items=[{"qid": "q-gone", "kind": "text", "answer": "Answer"}],
    )

    assert result["results"] == [{"qid": "q-gone", "outcome": "not_stuck"}]


def test_text_retries_once_after_the_first_write_reverts(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-notice",
            "label": "Notice",
            "kind": "text",
            "revertsTimes": 1,
        }],
        items=[{"qid": "q-notice", "kind": "text", "answer": "Two weeks"}],
    )

    assert result["results"] == [
        {"qid": "q-notice", "outcome": "retry_filled"}
    ]
    assert result["values"]["Notice"] == "Two weeks"
    assert result["attempts"]["Notice"] == 2


def test_text_stops_after_exactly_two_failed_attempts(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-notice",
            "label": "Notice",
            "kind": "text",
            "reverts": True,
        }],
        items=[{"qid": "q-notice", "kind": "text", "answer": "Two weeks"}],
    )

    assert result["results"] == [{"qid": "q-notice", "outcome": "not_stuck"}]
    assert result["values"]["Notice"] == ""
    assert result["attempts"]["Notice"] == 2


def test_unverified_text_is_not_retried(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{"qid": "q-notice", "label": "Notice", "kind": "text"}],
        items=[{"qid": "q-notice", "kind": "text", "answer": "Two weeks"}],
        freeze_frames=True,
    )

    assert result["results"] == [
        {"qid": "q-notice", "outcome": "filled_unverified"}
    ]
    assert result["attempts"]["Notice"] == 1


def test_listbox_retries_once_when_the_first_option_click_is_cancelled(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{
            "qid": "q-country",
            "label": "Country",
            "kind": "listboxButton",
            "listbox": ["Canada", "Mexico"],
            "optionFailures": 1,
        }],
        items=[{"qid": "q-country", "kind": "combobox", "answer": "Canada"}],
    )

    assert result["results"] == [
        {"qid": "q-country", "outcome": "retry_filled"}
    ]
    assert result["values"]["Country"] == "Canada"
    assert result["events"]["Country"].count("option:click:Canada") == 2
