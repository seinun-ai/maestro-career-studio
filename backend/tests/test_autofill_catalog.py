import pytest

from app.services import autofill_catalog as cat
from app.services import autofill_slots

PROFILE = {
    "personal": {"first_name": "Sample", "city": "Springfield"},
    "work_auth": {"status": "stem_opt", "sponsorship_future": True},
    "eeo": {"veteran_status": "not_veteran"},
    "preferences": {"willing_to_relocate": True, "how_heard": "LinkedIn"},
    "education": [
        {"school": "State University", "degree": "Master's", "discipline": "Business Analytics", "end_year": "2024"},
        {"school": "City College", "degree": "Bachelor's", "discipline": "Engineering", "end_year": "2019"},
    ],
    "custom": [{"question": "Do you have a clearance?", "answer": "No"}],
}
EMPLOYMENT = [
    {"employer": "Acme", "title": "Analyst", "location": "Remote", "start_date": "Aug 2021",
     "end_date": None, "current": True, "description": "Built dashboards"},
    {"employer": "Beta", "title": "Intern", "location": "", "start_date": "2020-05",
     "end_date": "08/2020", "current": False, "description": ""},
]


def facts():
    return cat.build(PROFILE, EMPLOYMENT, ["Python", "SQL"])


def test_every_education_entry_is_its_own_slots():
    f = facts()
    assert f["education.1.school"].value == "City College" and f["education.1.school"].policy == "flag"
    assert f["education.1.school"].describe == "education entry 2: school"


def test_experience_dates_normalise_and_a_current_job_has_no_end():
    f = facts()
    assert f["experience.0.start"].value == "2021-08" and "experience.0.end" not in f
    assert f["experience.0.current"].value == "Yes"
    assert (f["experience.1.start"].value, f["experience.1.end"].value) == ("2020-05", "2020-08")


def test_an_empty_resume_field_is_not_a_fact():
    f = facts()
    assert "experience.1.location" not in f and "experience.1.description" not in f


def test_codes_become_words_a_form_would_show():
    f = facts()
    assert f["work_auth.status"].value == "F-1 STEM OPT extension" and f["work_auth.status"].policy == "exact"
    assert f["eeo.veteran_status"].value == "I am not a protected veteran"
    assert f["work_auth.sponsorship_future"].value == "Yes"


def test_skills_are_a_set_and_custom_answers_carry_their_question():
    f = facts()
    assert f["skills"].value == ("Python", "SQL")
    assert f["custom.0"].describe == "saved answer to: Do you have a clearance?"


def test_descriptions_never_carry_values():
    for fact in facts().values():
        if not fact.slot.startswith("custom"):
            assert str(fact.value) not in fact.describe


def test_a_legacy_single_education_object_and_the_size_cap():
    assert cat.build({"education": {"school": "Old U"}}, [], [])["education.0.school"].value == "Old U"
    assert len(cat.build(PROFILE, [dict(EMPLOYMENT[1]) for _ in range(20)], [])) <= cat.MAX_SLOTS


def test_a_self_described_gender_is_the_description_not_the_code():
    f = cat.build({"eeo": {"gender": "self_describe", "gender_self_describe": "Agender"}}, [], [])
    assert f["eeo.gender"].value == "Agender"


@pytest.mark.parametrize("slot, policy", [
    ("experience.0.title", "flag"), ("skills", "flag"), ("custom.3", "flag"),
    ("education.1.school", "flag"), ("work_auth.status", "exact"), ("preferences.how_heard", "any"),
])
def test_resume_facts_and_saved_answers_are_flag_policy(slot, policy):
    assert autofill_slots.policy_for(slot) == policy


@pytest.mark.parametrize("text, expected", [
    ("Aug 2021", "2021-08"), ("August 2021", "2021-08"), ("Sept. 2019", "2019-09"),
    ("2021-08-01", "2021-08"), ("2021-8", "2021-08"), ("08/2021", "2021-08"), ("2021", "2021"),
    ("Present", None), ("", None), (None, None), ("Foo 2021", None),
    ("13/2021", None), ("00/2021", None), ("2021-00", None), ("2021-13", None), ("2021-12", "2021-12"),
])
def test_ym_reads_the_resume_date_shapes(text, expected):
    assert cat.ym(text) == expected


def test_a_hand_edited_profile_of_the_wrong_shapes_builds_what_it_can():
    f = cat.build({"personal": "Sample", "education": "State University", "custom": {"q": "a"},
                   "preferences": {"how_heard": "LinkedIn"}}, [], [])
    assert list(f) == ["preferences.how_heard"]


def test_exact_slots_are_described_in_words_a_form_uses():
    f = cat.build({
        "work_auth": {"status": "opt", "authorized_now": True, "sponsorship_now": False,
                      "sponsorship_future": True, "authorization_expires_on": "2027-01-01",
                      "countries_authorized": ["United States"]},
        "eligibility": {"over_18": True, "previously_employed_here": False, "non_compete": False},
        "eeo": {"gender": "female", "race_ethnicity": ["Asian"], "hispanic_latino": False,
                "veteran_status": "not_veteran", "disability_status": "no"},
    }, [], [])
    assert f["work_auth.sponsorship_now"].describe == "needs employer visa sponsorship now (yes/no)"
    assert f["work_auth.authorized_now"].describe == "legally authorized to work in the country now (yes/no)"
    assert f["work_auth.sponsorship_future"].describe == "will need visa sponsorship in the future (yes/no)"
    assert f["work_auth.status"].describe == "current work-authorization / visa status"
    assert f["eligibility.over_18"].describe == "is 18 or older (yes/no)"
    assert f["eligibility.previously_employed_here"].describe == "has worked for this company before (yes/no)"
    exact = [fact for fact in f.values() if fact.policy == "exact"]
    assert len(exact) == 14
    for fact in exact:
        assert ":" not in fact.describe, fact.slot  # hand-written, not the slot's path
        assert str(fact.value) not in fact.describe, fact.slot
