from app.services import autofill_slots as slots


def test_flatten_keeps_answered_leaves_as_text():
    profile = {
        "personal": {"first_name": "Ada", "phone": ""},
        "work_auth": {"sponsorship_now": False, "countries_authorized": ["US", "CA"]},
        "preferences": {"notice_period": "0"},
        "note": "not a section",
    }
    assert slots.flatten(profile) == {
        "personal.first_name": "Ada",
        "work_auth.sponsorship_now": "No",
        "work_auth.countries_authorized": "US, CA",
        "preferences.notice_period": "0",
    }


def test_the_policy_is_by_section():
    assert slots.policy_for("work_auth.sponsorship_now") == "exact"
    assert slots.policy_for("eligibility.over_18") == "exact"
    assert slots.policy_for("eeo.gender") == "exact"
    assert slots.policy_for("education.discipline") == "flag"
    assert slots.policy_for("personal.country") == "flag"
    assert slots.policy_for("preferences.how_heard") == "any"
    # A known_value field arrives without a slot: treated as a factual claim.
    assert slots.policy_for(None) == "flag"


def test_criteria_offer_every_slot_plus_free_text_and_none():
    criteria = slots.slot_criteria({"education.discipline": "Business analytics"})
    assert set(criteria) == {"education.discipline", slots.FREE_TEXT, slots.NO_SLOT}
    # Labels only — the VALUE never appears in the slot question.
    assert "Business analytics" not in str(criteria)


def test_education_is_a_list_and_its_most_recent_entry_is_the_slot():
    """The stored shape (§13 `autofill-education-shape`): a list, most recent first,
    or one legacy object. Other list sections (`custom` Q&A) are not slots — the
    fast model's prompt already carries them."""
    profile = {
        "education": [{"discipline": "Business analytics", "school": "UT"},
                      {"discipline": "Economics"}],
        "custom": [{"question": "Pronouns", "answer": "she/her"}],
    }
    assert slots.flatten(profile) == {
        "education.discipline": "Business analytics",
        "education.school": "UT",
    }
    assert slots.flatten({"education": {"degree": "MS"}}) == {"education.degree": "MS"}
    assert slots.flatten({"education": []}) == {}
