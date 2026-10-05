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
    "Are you eligible to work in the United States?",
    "Do you have the right to work in Canada?",
    "Do you need a work permit?",
    "Are you a permanent resident?",
    "Do you hold a green card?",
    "Will you need an H-1B transfer?",
    "Are you at least 18 years old?",
    "Are you comfortable with a hybrid schedule?",
    "Can you commute to our Boston office?",
    "Can you work three days per week on site?",
    "This role is based in our San Francisco office. Is that ok?",
    "When can you start?",
    "What is your notice period?",
    "Do you currently reside in the United States?",
    "Are you over 18?",
    "Are you 18 years of age or older?",
    "Are you willing to commute?",
    "Where do you currently reside?",
    "Are you able to work in the office three days a week?",
])
def test_screening_questions_are_recognized_by_their_words(question):
    assert answer_flags.is_screening(question, None)


@pytest.mark.parametrize("question", [
    "First name", "Why do you want to work at Acme?", "LinkedIn profile",
    "How did you hear about us?", "Which cohorts are you interested in?",
    "How did you hear about us, e.g. a career fair at your university?",
    "Tell us about your residency program experience",
    "Describe a project you are proud of",
    "Describe your experience with hybrid cloud architectures",
    "How do you spend your commute?",
    "Tell us about your 18 months of experience with Kafka",
    "We have 18 offices worldwide. Why us?",
    "Where does your data reside in a typical pipeline?",
    "Describe what you'd add to the culture in our NYC office",
    "Describe a time you worked in the office of the CTO",
])
def test_ordinary_questions_are_not_screening(question):
    assert not answer_flags.is_screening(question, None)


def test_an_exact_policy_slot_is_screening_whatever_its_words():
    assert answer_flags.is_screening("Status", "work_auth.status")


def test_an_eeo_slot_is_not_a_screening_question():
    assert not answer_flags.is_screening("Gender", "eeo.gender")


@pytest.mark.parametrize("question", ["Gender", "Race / Ethnicity", "Are you Hispanic or Latino?",
                                      "Veteran status", "Disability status", "Sexual orientation",
                                      "What are your pronouns?", "Do you identify as LGBTQ+?",
                                      "Do you identify as queer?"])
def test_eeo_questions_are_recognized_by_their_words(question):
    assert answer_flags.is_eeo(question, None)


@pytest.mark.parametrize("question", ["Preferred name", "Which programming languages do you use?",
                                      "How did you hear about us?"])
def test_ordinary_questions_are_not_eeo(question):
    assert not answer_flags.is_eeo(question, None)


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


AUTHORIZED = {"work_auth": {"authorized_now": True, "sponsorship_now": False}}
QUIET += [
    ("authorized without the need for sponsorship, Yes",
     _field("Are you legally authorized to work in the United States without the need for sponsorship?",
            "Yes", "profile", slot="work_auth.authorized_now"), AUTHORIZED),
    ("authorized without restriction, Yes",
     _field("Are you authorized to work in the US without restriction?", "Yes", "profile",
            slot="work_auth.authorized_now"), AUTHORIZED),
    ("authorized without restriction, No: an ambiguous cue stays quiet both ways",
     _field("Are you authorized to work in the US without restriction?", "No", "profile",
            slot="work_auth.authorized_now"), AUTHORIZED),
    ("a lead-in clause's negation is not the question's",
     _field("If you do not have a degree, are you still willing to relocate?", "Yes", "profile",
            slot="preferences.willing_to_relocate"), {"preferences": {"willing_to_relocate": True}}),
    ("work without sponsorship, Yes",
     _field("Can you work in the US without sponsorship?", "Yes", "profile",
            slot="work_auth.sponsorship_now"), AUTHORIZED),
    ("a long essay a model wrote",
     _field(ON_SITE_WEEKLY, "x" * 201, "written"), {}),
]
QUIET += [
    ("a sponsorship answer read off the saved ones",
     _field("Will you now or in the future require sponsorship?", "No", "inferred",
            slot="derived.sponsorship_now_or_future"),
     {"work_auth": {"sponsorship_now": False, "sponsorship_future": False}}),
    ("a citizenship answer read off the saved status",
     _field("Are you a US citizen?", "Yes", "inferred", slot="derived.us_citizen"),
     {"work_auth": {"status": "citizen"}}),
    ("agreeing to the application's terms",
     _field("I agree to the terms", "Yes", "inferred", slot="derived.agrees_to_terms"), {}),
    ("a language level", _field("Language", "English", "inferred", slot="languages.0.language"), {}),
    ("a phone number in another format",
     _field("Phone", "+1 555-123-4567", "profile", slot="personal.phone"),
     {"personal": {"phone": "(555) 123-4567"}}),
    ("the same month written out",
     _field("Graduation date", "May 2026", "profile", slot="education.0.end_date"),
     {"education": [{"end_date": "2026-05"}]}),
    ("the same month as MM/YYYY",
     _field("Graduation date", "05/2026", "profile", slot="education.0.end_date"),
     {"education": [{"end_date": "2026-05"}]}),
    ("today's date, however it is written",
     _field("Date", "10/04/2026", "profile", slot="derived.today"), {}),
    ("a question that names another sentence's negation",
     _field("We do not offer relocation assistance. Are you willing to relocate?", "Yes", "profile",
            slot="preferences.willing_to_relocate"), {"preferences": {"willing_to_relocate": True}}),
    ("a curly-apostrophe negation flips the saved No",
     _field("Won\u2019t you need sponsorship?", "Yes", "profile", slot="work_auth.sponsorship_now"),
     {"work_auth": {"sponsorship_now": False}}),
    ("an EEO answer you chose yourself",
     _field("Veteran status", "No", "you", eeo=True), {}),
    ("a veteran answer when the veteran answer is saved",
     _field("Veteran status", "No", "inferred", eeo=True), {"eeo": {"veteran_status": "not_veteran"}}),
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


DIFFERS += [
    ("male against a saved female",
     _field("Gender", "Male", "profile", slot="eeo.gender", eeo=True), {"eeo": {"gender": "female"}}),
    ("US against a saved Russia",
     _field("Country", "US", "profile", slot="personal.country"), {"personal": {"country": "Russia"}}),
    ("a negated question answered with the saved No itself",
     _field("Will you NOT require sponsorship?", "No", "profile", slot="work_auth.sponsorship_now"),
     {"work_auth": {"sponsorship_now": False}}),
    ("a negation in another sentence does not flip the question",
     _field("We do not offer relocation assistance. Are you willing to relocate?", "No", "profile",
            slot="preferences.willing_to_relocate"), {"preferences": {"willing_to_relocate": True}}),
    ("another phone number",
     _field("Phone", "+1 555-999-0000", "profile", slot="personal.phone"),
     {"personal": {"phone": "(555) 123-4567"}}),
    ("another month", _field("Graduation date", "June 2026", "profile", slot="education.0.end_date"),
     {"education": [{"end_date": "2026-05"}]}),
]


@pytest.mark.parametrize(("field", "profile"), [case[1:] for case in DIFFERS],
                         ids=[case[0] for case in DIFFERS])
def test_an_answer_unlike_the_saved_one_is_flagged(field, profile):
    assert _ids(field, profile) == ["differs_from_profile"]


def test_a_short_written_answer_to_a_screening_question_is_flagged():
    assert _ids(_field(ON_SITE_WEEKLY, "x" * 200, "written")) == ["guessed_screening"]


def test_an_unsaved_voluntary_question_is_judged_by_its_own_key():
    field = _field("Veteran status", "No", "inferred", eeo=True)
    assert _ids(field, {"eeo": {"gender": "female"}}) == ["eeo_without_saved_answer"]


@pytest.mark.parametrize("slot", ["languages.0.language", "languages.1.level", "derived.agrees_to_terms"])
def test_a_language_or_the_terms_are_no_knock_out_slot(slot):
    assert not answer_flags.is_screening("Language", slot)


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
