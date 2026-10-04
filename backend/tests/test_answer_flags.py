"""Risk flags on filled answers (docs/entities/filled-answers.md).
Phase 4's auto-submit rule reads
`is_screening`, so its pattern list is pinned here question by question."""

import pytest
from pydantic import ValidationError

from app.schemas.filled_answers import FilledAnswersCreate, FilledField
from app.services import answer_flags
from app.services.autofill_catalog import build

ON_SITE_WEEKLY = ("This role requires you to be in the office 4–5 days a week for the 3-month "
                "duration of the internship. Does that work for you?")
CLEARANCE_QUESTION = "Current/active clearance level or eligibility"
ON_SITE_FULL_TIME = "Able and willing to work 100% onsite at our headquarters"
COHORT_CHOICES = ["Summer 2027 (SF)", "Summer 2027 (NYC)", "Fall 2027", "Winter 2027 (Toronto)",
                  "Spring 2028"]
CITY_CHOICES = ["San Francisco", "New York", "Toronto"]
SEASON_CHOICES = ["Spring (Jan–Apr)", "Summer (May–Aug)", "Summer (Jun–Sep)"]


def _field(question, answer, source, **extra):
    return {"question": question, "section": None, "required": False, "answer": answer,
            "options_count": None, "source": source, "slot": None, "eeo": False,
            "edited_by_you": False, "eeo_answered": False, **extra}


def _ids(field, profile=None):
    profile = profile or {}
    facts = build(profile, [], [])
    return [flag["id"] for flag in answer_flags.flags_for(field, facts,
                                                          answer_flags.saved_eeo(profile))]


@pytest.mark.parametrize("question", [
    ON_SITE_WEEKLY, CLEARANCE_QUESTION, ON_SITE_FULL_TIME,
    "Are you legally authorized to work in the United States?",
    "Will you now or in the future require visa sponsorship?",
    "What is your current visa status?",
    "Are you willing to relocate?",
    "Can you work in-office three days a week?",
    "Are you able to work in person at our Austin office?",
    "Are you a US citizen?",
    "Do you hold a bachelor's degree in computer science?",
    "What is your expected graduation date?",
    "Are you currently enrolled in a degree program?",
    "What is your earliest start date?",
    "Are you available for the full 12 weeks?",
])
def test_screening_questions_are_recognized_by_their_words(question):
    assert answer_flags.is_screening(question, None)


@pytest.mark.parametrize("question", [
    "First name", "Why do you want to work at Acme?", "LinkedIn profile",
    "How did you hear about us?", "Which cohorts are you interested in?",
])
def test_ordinary_questions_are_not_screening(question):
    assert not answer_flags.is_screening(question, None)


def test_an_exact_policy_slot_is_screening_whatever_its_words():
    assert answer_flags.is_screening("Status", "work_auth.status")


def test_an_eeo_slot_is_not_a_screening_question():
    assert not answer_flags.is_screening("Gender", "eeo.gender")


@pytest.mark.parametrize("question", ["Gender", "Race / Ethnicity", "Are you Hispanic or Latino?",
                                      "Veteran status", "Disability status", "Sexual orientation"])
def test_eeo_questions_are_recognized_by_their_words(question):
    assert answer_flags.is_eeo(question, None)


SCREENING_CASES = [
    ("on-site, inferred", _field(ON_SITE_WEEKLY, "No", "inferred"), {},
     ["guessed_screening"]),
    ("on-site, profile says yes",
     _field(ON_SITE_WEEKLY, "No", "profile", slot="preferences.willing_to_relocate"),
     {"preferences": {"willing_to_relocate": True}}, ["differs_from_profile"]),
    ("on-site, profile says no",
     _field(ON_SITE_WEEKLY, "No", "profile", slot="preferences.willing_to_relocate"),
     {"preferences": {"willing_to_relocate": False}}, []),
    ("clearance", _field(CLEARANCE_QUESTION, "Eligible", "inferred"), {},
     ["guessed_screening"]),
    ("on-site, full time", _field(ON_SITE_FULL_TIME, "Yes", "inferred"), {}, ["guessed_screening"]),
    ("cohorts", _field("Which cohorts are you interested in?", COHORT_CHOICES, "inferred",
                              options_count=5), {}, ["ticked_everything"]),
    ("cities", _field("Which offices would you relocate to?", CITY_CHOICES, "inferred",
                             options_count=3), {}, ["guessed_screening", "ticked_everything"]),
    ("seasons", _field("Spring, or Summer 2027?", SEASON_CHOICES, "inferred", options_count=3),
     {}, ["ticked_everything"]),
    ("eeo decline, nothing saved", _field("Gender", "I prefer not to answer", "inferred", eeo=True),
     {}, ["eeo_without_saved_answer"]),
]


@pytest.mark.parametrize(("field", "profile", "expected"), [case[1:] for case in SCREENING_CASES],
                         ids=[case[0] for case in SCREENING_CASES])
def test_the_screening_answers_are_flagged(field, profile, expected):
    assert _ids(field, profile) == expected


QUIET = [
    ("two of two ticked", _field("Which shifts?", ["Day", "Night"], "inferred", options_count=2), {}),
    ("you chose it", _field(ON_SITE_WEEKLY, "No", "inferred", edited_by_you=True), {}),
    ("a reversed question flips the saved No",
     _field("Will you be able to work without visa sponsorship?", "Yes", "profile",
            slot="work_auth.sponsorship_now"), {"work_auth": {"sponsorship_now": False}}),
    ("a richer wording of the saved value",
     _field("Highest degree", "Master of Science (MS)", "profile", slot="education.0.degree"),
     {"education": [{"degree": "Master of Science"}]}),
    ("a saved EEO answer", _field("Gender", "Female", "profile", slot="eeo.gender", eeo=True),
     {"eeo": {"gender": "female"}}),
    ("an EEO question left blank", _field("Veteran status", None, "inferred", eeo=True), {}),
    ("a slot the profile does not hold", _field("Job title", "Engineer", "resume",
                                                slot="experience.0.title"), {}),
]


@pytest.mark.parametrize(("field", "profile"), [case[1:] for case in QUIET],
                         ids=[case[0] for case in QUIET])
def test_answers_that_need_no_second_look_are_not_flagged(field, profile):
    assert _ids(field, profile) == []


DIFFERS = [
    ("a plain yes against a saved no",
     _field("Do you need visa sponsorship now?", "Yes", "profile", slot="work_auth.sponsorship_now"),
     {"work_auth": {"sponsorship_now": False}}),
    ("another degree", _field("Highest degree", "Bachelor's", "profile", slot="education.0.degree"),
     {"education": [{"degree": "Master of Science"}]}),
]


@pytest.mark.parametrize(("field", "profile"), [case[1:] for case in DIFFERS],
                         ids=[case[0] for case in DIFFERS])
def test_an_answer_unlike_the_saved_one_is_flagged(field, profile):
    assert _ids(field, profile) == ["differs_from_profile"]


def test_every_flag_carries_its_one_line_reason():
    flags = answer_flags.flags_for(_field(CLEARANCE_QUESTION, "Eligible", "inferred"), {}, set())
    assert flags == [{"id": "guessed_screening",
                      "reason": "A screening question with no saved answer behind it."}]


def test_the_wire_refuses_an_unknown_source_and_stray_keys():
    with pytest.raises(ValidationError):
        FilledField(question="Q", answer="A", source="kb")
    with pytest.raises(ValidationError):
        FilledField(question="Q", answer="A", source="profile", value="A")


def test_an_upload_names_what_it_attached():
    with pytest.raises(ValidationError):
        FilledField(question="Resume", answer="cv.pdf", source="upload")
    assert FilledField(question="Resume", answer="cv.pdf", source="upload", slot="resume").slot == "resume"


def test_a_post_needs_at_least_one_field():
    with pytest.raises(ValidationError):
        FilledAnswersCreate(channel="agent", fields=[])
