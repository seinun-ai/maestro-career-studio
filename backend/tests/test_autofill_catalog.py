import re
from datetime import date
from typing import get_args

import pytest

from app.services import autofill_catalog as cat
from app.schemas.autofill_profile import WorkAuthStatus
from app.services import autofill_slots

PROFILE = {
    "personal": {"first_name": "Sample", "city": "Springfield"},
    "work_auth": {"status": "stem_opt", "sponsorship_future": True},
    "eeo": {"veteran_status": "no"},
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
    assert f["eeo.veteran_status"].value == "No, I am not a veteran"
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
    # (Today's date is derived from the clock alone, so it is always there.)
    assert list(f) == ["preferences.how_heard", "derived.today"]


def test_exact_slots_are_described_in_words_a_form_uses():
    f = cat.build({
        "work_auth": {"status": "opt", "authorized_now": True, "sponsorship_now": False,
                      "sponsorship_future": True, "authorization_expires_on": "2027-01-01",
                      "countries_authorized": ["United States"]},
        "eligibility": {"over_18": True, "previously_employed_here": False, "non_compete": False},
        "eeo": {"gender": "female", "race_ethnicity": ["Asian"], "hispanic_latino": False,
                "veteran_status": "no", "disability_status": "no"},
    }, [], [])
    assert f["work_auth.sponsorship_now"].describe == "needs employer visa sponsorship now (yes/no)"
    assert f["work_auth.authorized_now"].describe == "legally authorized to work in the country now (yes/no)"
    assert f["work_auth.sponsorship_future"].describe == "will need visa sponsorship in the future (yes/no)"
    assert f["work_auth.status"].describe == "current work-authorization / visa status"
    assert f["eligibility.over_18"].describe == "is 18 or older (yes/no)"
    assert f["eligibility.previously_employed_here"].describe == "has worked for this company before (yes/no)"
    exact = [fact for fact in f.values() if fact.policy == "exact"]
    assert len(exact) == 16  # 14 profile answers, the citizenship and "now or in the future" derived
    for fact in exact:
        assert ":" not in fact.describe, fact.slot  # hand-written, not the slot's path
        assert str(fact.value) not in fact.describe, fact.slot


# ---------- derived facts (fill-engine plan Task 9): their own `derived.*`
# section, so /map is told honestly where each one comes from.

TODAY = date(2026, 9, 26)


def derived(profile, **kw):
    return {slot: fact for slot, fact in cat.build(profile, [], [], today=TODAY, **kw).items()
            if slot.startswith("derived.")}


def test_full_name_is_the_legal_first_and_last_name():
    f = derived({"personal": {"first_name": " Sample ", "last_name": "Person", "preferred_name": "Sam"}})
    assert f["derived.full_name"].value == "Sample Person"
    assert f["derived.full_name"].describe == "your full legal name, for name and signature boxes"
    assert f["derived.full_name"].policy == "flag"


@pytest.mark.parametrize("personal", [{"first_name": "Sample"}, {"last_name": "Person"}, {"first_name": " ", "last_name": "P"},
                                      {"preferred_name": "Sam"}, {}])
def test_a_full_name_is_never_invented_from_half_of_one(personal):
    assert "derived.full_name" not in derived({"personal": personal})


def test_today_is_an_iso_date_from_the_injected_clock():
    f = derived({})
    assert f["derived.today"].value == "2026-09-26"
    assert f["derived.today"].describe == "today's date, for a date the applicant signs or fills in today"
    assert f["derived.today"].policy == "any"


def test_today_defaults_to_the_real_clock():
    assert cat.build({}, [], [])["derived.today"].value == date.today().isoformat()


@pytest.mark.parametrize("status", get_args(WorkAuthStatus))
def test_us_citizen_is_derived_from_every_work_authorization_status(status):
    """Every status the profile can store answers it: only a citizen is one."""
    f = derived({"work_auth": {"status": status}})
    assert f["derived.us_citizen"].value == ("Yes" if status == "citizen" else "No")
    assert f["derived.us_citizen"].describe == "is a US citizen (yes/no; derived from the applicant's work authorization)"
    # A knockout answer: it maps only at the exact floor, and a near miss is refused.
    assert f["derived.us_citizen"].policy == "exact"


@pytest.mark.parametrize("work_auth", [{}, {"status": None}, {"status": ""}, {"status": "martian"},
                                       {"authorized_now": True}, "citizen"])
def test_an_unknown_status_derives_no_citizenship(work_auth):
    assert "derived.us_citizen" not in derived({"work_auth": work_auth})


@pytest.mark.parametrize("stored", ["Immedietly", "Immediately", "immediate", "ASAP", "right away", "Now",
                                    "available now", "asap!", " Available immediately. ", "Right  away",
                                    "Immediatly", "Immediate start", "Available: now"])
def test_an_immediate_start_is_also_a_date(stored):
    f = cat.build({"preferences": {"earliest_start_date": stored}}, [], [], today=TODAY)
    # The words stay the answer to a question asked in words…
    assert f["preferences.earliest_start_date"].value == stored.strip()
    # …and a date box gets a date.
    assert f["derived.earliest_start_date"].value == "2026-09-26"
    assert f["derived.earliest_start_date"].describe == "the earliest date you can start, as a calendar date"
    assert f["derived.earliest_start_date"].policy == "any"


@pytest.mark.parametrize("stored", ["2 weeks notice", "January 2027", "known in a month", "", None,
                                    "2 weeks from now", "Not immediately; 2 weeks notice", "not available right away"])
def test_a_start_that_is_not_immediate_derives_no_date(stored):
    f = cat.build({"preferences": {"earliest_start_date": stored}}, [], [], today=TODAY)
    assert "derived.earliest_start_date" not in f


def test_desired_salary_is_described_in_the_words_forms_ask_with():
    f = cat.build({"preferences": {"desired_salary": "80000"}}, [], [])
    assert f["preferences.desired_salary"].describe == (
        "desired salary, compensation or salary requirements (expected pay)")


def test_the_phone_and_street_address_say_what_they_are_not():
    """Live Workday (2026-09-27): "Phone Extension" got the phone number and
    "Address Line 2" got line 1, because /map offered only "personal: phone"
    and "personal: address". Each is described by what it IS, and by the
    neighbouring boxes it never answers."""
    f = cat.build({"personal": {"phone": "555-0100", "address": "1 Main St"}}, [], [])
    phone, address = f["personal.phone"].describe, f["personal.address"].describe
    for described in (phone, address):
        assert not described.startswith("personal:"), described
    assert "full phone number" in phone
    for never in ("extension", "fax", "country calling code"):
        assert never in phone, never
    assert "line 1" in address
    for never in ("second address line", "apartment", "county"):
        assert never in address, never


def test_derived_descriptions_carry_no_values():
    f = cat.build({"personal": {"first_name": "Sample", "last_name": "Person"}, "work_auth": {"status": "citizen"},
                   "preferences": {"earliest_start_date": "Immedietly"}}, [], [], today=TODAY)
    for slot in ("derived.full_name", "derived.today", "derived.us_citizen", "derived.earliest_start_date"):
        assert str(f[slot].value) not in f[slot].describe, slot


def test_derived_facts_survive_the_size_cap():
    many = [{"employer": f"E{i}", "title": "T", "location": "L", "description": "D", "start_date": "2020-01",
             "end_date": "2021-01"} for i in range(8)]
    f = cat.build({"personal": {"first_name": "A", "last_name": "B"}, "work_auth": {"status": "opt"},
                   "custom": [{"question": f"q{i}", "answer": "a"} for i in range(30)]}, many, ["x"] * 50, today=TODAY)
    assert {"derived.full_name", "derived.today", "derived.us_citizen"} <= set(f)


@pytest.mark.parametrize("slot, policy", [
    ("derived.us_citizen", "exact"), ("derived.full_name", "flag"), ("derived.today", "any"),
    ("derived.earliest_start_date", "any"),
])
def test_derived_policies_come_from_policy_for(slot, policy):
    """One place decides a slot's policy, derived slots included."""
    assert autofill_slots.policy_for(slot) == policy
    f = cat.build({"personal": {"first_name": "A", "last_name": "B"}, "work_auth": {"status": "tn"},
                   "preferences": {"earliest_start_date": "ASAP"}}, [], [], today=TODAY)
    assert f[slot].policy == policy


# ---------- review: "previously employed by <this company>" from the work history

def test_the_jobs_company_in_the_history_derives_previously_employed_yes():
    f = cat.build({"eligibility": {"previously_employed_here": False}},
                  [{"employer": "Soylent Consultancy Services Ltd.", "title": "Engineer"}], [],
                  company="SOYLENT CONSULTANCY SERVICES")
    fact = f["derived.previously_employed_here"]
    assert fact.value == "Yes, previously" and "from the work history" in fact.describe
    # The standing answer is company-agnostic: for THIS job it would be wrong.
    assert "eligibility.previously_employed_here" not in f


@pytest.mark.parametrize("company", [None, "", "Soylent"])
def test_no_company_or_a_parent_or_subsidiary_name_derives_nothing_and_keeps_the_standing_answer(company):
    """No company known, or one that is the start of an employer's name: the history cannot say No, so
    the question is asked as before."""
    f = cat.build({"eligibility": {"previously_employed_here": False}},
                  [{"employer": "Soylent Consultancy Services", "title": "Engineer"}], [], company=company)
    assert "derived.previously_employed_here" not in f
    assert f["eligibility.previously_employed_here"].value == "No"


HISTORY = [{"employer": "Initech", "title": "Engineer", "start_date": "2018-01", "end_date": "2020-06"},
           {"employer": "Hooli Inc.", "title": "Lead", "start_date": "2020-07", "current": True}]


def test_a_history_with_jobs_and_none_at_the_company_derives_no():
    f = cat.build({"eligibility": {"previously_employed_here": False}}, HISTORY, [], company="Acme")
    fact = f["derived.previously_employed_here"]
    assert fact.value == "No" and fact.yes_no and "from the work history" in fact.describe
    assert fact.policy == "flag"   # the receipt reads a derived fact as `inferred`
    assert "eligibility.previously_employed_here" not in f   # one answer for this job, the history's


def test_a_match_is_still_yes_not_no():
    f = cat.build({}, HISTORY, [], company="Initech, Inc.")
    assert f["derived.previously_employed_here"].value == "Yes, previously"
    f = cat.build({}, HISTORY, [], company="HOOLI")
    assert f["derived.previously_employed_here"].value == "Yes, currently"


def test_an_empty_history_leaves_the_question_unanswered():
    f = cat.build({"eligibility": {"previously_employed_here": False}}, [], [], company="Acme")
    assert "derived.previously_employed_here" not in f
    assert f["eligibility.previously_employed_here"].value == "No"


@pytest.mark.parametrize("company, expected", [
    ("Acme, Globex, or Initech", "Yes, previously"),   # one of three matches
    ("Acme, Globex or Umbrella", "No"),                # none of three does
    ("Acme / Hooli", "Yes, currently"),
    ("Globex and Sons", "No"),                         # "and" inside a name still reads as a name
])
def test_a_string_naming_several_companies_is_no_only_when_none_matches(company, expected):
    f = cat.build({}, HISTORY, [], company=company)
    assert f["derived.previously_employed_here"].value == expected


def test_a_whole_name_that_holds_and_still_matches_whole():
    f = cat.build({}, [{"employer": "Globex and Sons", "title": "Analyst"}], [], company="Globex and Sons")
    assert f["derived.previously_employed_here"].value == "Yes, previously"


def test_a_long_history_is_compared_whole_not_as_far_as_the_catalog_lists_it():
    """The catalog lists MAX_EXPERIENCE jobs, but a job past the limit is still a job: Yes for a match
    there, and No only after every job was compared (owner, 2026-10-14)."""
    jobs = [{"employer": f"Firm{i}", "title": "Engineer"} for i in range(cat.MAX_EXPERIENCE)]
    long_history = jobs + [{"employer": "Acme", "title": "Analyst", "current": True}]
    assert f"experience.{cat.MAX_EXPERIENCE}.employer" not in cat.build({}, long_history, [], company="Zeta")
    assert cat.build({}, long_history, [], company="Zeta")["derived.previously_employed_here"].value == "No"
    assert cat.build({}, long_history, [], company="Acme")["derived.previously_employed_here"].value == "Yes, currently"
    assert cat.build({}, long_history, [], company="Firm3")["derived.previously_employed_here"].value == "Yes, previously"
    # …and a parent/subsidiary name past the limit still blocks the No.
    assert "derived.previously_employed_here" not in cat.build({}, long_history, [], company="Acme Web Services")


def test_a_standing_yes_outranks_an_inferred_no():
    """The user said they worked there: no job in the history changes their word."""
    f = cat.build({"eligibility": {"previously_employed_here": True}}, HISTORY, [], company="Acme")
    assert "derived.previously_employed_here" not in f
    assert f["eligibility.previously_employed_here"].value == "Yes"


def test_a_parent_and_its_subsidiary_are_not_a_no():
    f = cat.build({}, [{"employer": "Acme", "title": "Engineer"}], [], company="Acme Web Services")
    assert "derived.previously_employed_here" not in f


# ---------- the question names companies the job's company string does not (answer time)

def test_a_question_that_lists_an_employer_of_the_history_turns_the_no_into_yes():
    """An Acme application asks "Acme, Globex, or Initech?" and the history holds Initech: the derived
    No is about Acme only, so for this question the answer is Yes."""
    f = cat.build({}, HISTORY, [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    got = cat.named_employer_fact(f, "Have you worked for Acme, Globex, or Initech before?")
    assert got is not None and got.slot == "derived.previously_employed_here" and got.value == "Yes, previously"
    assert got.describe == f["derived.previously_employed_here"].describe and got.policy == "flag"
    assert cat.named_employer_fact(f, "Employed by", ["Former employee of HOOLI, Inc."]).value == "Yes, currently"
    assert cat.named_employer_fact(f, "Previously employed by Acme or Initech?").value == "Yes, previously"


@pytest.mark.parametrize("question, options", [
    ("Have you worked for Acme or Globex before?", ()),       # none is in the history
    ("Were you a member of the Initechnical society?", ()),   # not a company of the history
    ("Willing to relocate?", ()),
    ("Please give the dates in the box below.", ()),
])
def test_a_question_that_lists_no_employer_of_the_history_keeps_the_no(question, options):
    assert cat.named_employer_fact(cat.build({}, HISTORY, [], company="Acme"), question, options) is None


def test_only_the_companies_a_question_lists_are_compared_not_any_word_in_its_text():
    """A history employer called "Field" or "Freelance" is not named by "the field below" or "…or freelance"."""
    history = [{"employer": "Field", "title": "Engineer"}, {"employer": "Freelance", "title": "Consultant"}]
    f = cat.build({}, history, [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    for question in ("Have you worked for Acme? Please give dates in the box below.",
                     "Have you ever worked for Acme as an employee or freelance?",
                     "Have you worked for Acme, as a contractor, or in a freelance role?"):
        assert cat.named_employer_fact(f, question) is None, question


@pytest.mark.parametrize("employer", ["Freelance", "Self-Employed", "Self employed", "Independent", "Contract",
                                      "Contractor", "Consultant", "Consulting", "Various", "Confidential",
                                      "Stealth", "Personal Project"])
def test_a_history_employer_that_is_no_company_is_never_named(employer):
    f = cat.build({}, [{"employer": employer, "title": "Engineer"}], [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    assert cat.named_employer_fact(f, f"Have you worked for Acme or {employer}?", [employer]) is None


def test_an_option_that_is_a_company_or_names_one_counts_as_listed():
    f = cat.build({}, HISTORY, [], company="Acme")
    assert cat.named_employer_fact(f, "Which of these did you work for?", ["Globex", "Initech"]).value \
        == "Yes, previously"
    assert cat.named_employer_fact(f, "Employment", ["Current employee of Hooli", "No"]).value == "Yes, currently"
    assert cat.named_employer_fact(f, "Employment", ["Yes", "No", "Not Applicable"]) is None


@pytest.mark.parametrize("history, question", [
    ("Acme Web Services", "Have you worked for Acme before?"),            # the history holds the subsidiary
    ("Acme", "Have you worked for Acme Web Services before?"),            # the history holds the parent
])
def test_a_parent_or_subsidiary_of_a_listed_company_is_asked_not_answered(history, question):
    f = cat.build({}, [{"employer": history, "title": "Engineer"}], [], company="Zeta")
    assert f["derived.previously_employed_here"].value == "No"
    assert cat.named_employer_fact(f, question) == cat.ASK_THE_USER
    # An exact match elsewhere in the list still wins: the answer is Yes, whatever else is akin.
    assert cat.named_employer_fact(f, f"Have you worked for {history}, or Zeta?").value == "Yes, previously"


# Every wording an employer of the history can turn up in. Whatever the parser makes of it, the answer is
# NEVER the derived No: Yes when the list parses, ask when it does not.
UNPARSED_MENTIONS = [
    ("Have you worked for any of the following companies: Initech, Globex, Acme?", ()),
    ("Have you worked for any of the following: Initech, Globex or Acme?", ()),
    ("Have you worked for Acme, Inc. or Initech, LLC?", ()),
    ("Have you worked at Acme, or at Initech?", ()),
    ("Have you worked for our affiliates (Globex, Initech)?", ()),
    ("Have you worked previously at Initech?", ()),
    ("Previous Initech employee?", ()),
    ("Have you interned at Initech?", ()),
    ("Initech, Globex or Acme: have you worked for any of them?", ()),
    ("Please include Initech and Globex", ()),
    ("Employment history", ["Yes, Initech", "No"]),
    ("Which company?", ["Initech"]),
    ("Have you worked for Acme?", ["Yes, I worked at Initech", "No"]),
]


@pytest.mark.parametrize("question, options", UNPARSED_MENTIONS)
def test_an_employer_of_the_history_mentioned_in_any_wording_is_never_a_no(question, options):
    f = cat.build({}, HISTORY, [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    got = cat.named_employer_fact(f, question, options)
    assert got is not None, (question, options)
    assert got == cat.ASK_THE_USER or got.value.startswith("Yes"), got


@pytest.mark.parametrize("question, options, parsed", [
    ("Have you worked for any of the following companies: Initech, Globex, Acme?", (), True),
    ("Have you worked for Acme, Inc. or Initech, LLC?", (), True),
    ("Have you worked at Acme, or at Initech?", (), True),
    ("Employment history", ["Yes, Initech", "No"], True),
    ("Previous Initech employee?", (), False),     # not a list the parser reads: the safety net asks
    ("Have you interned at Initech?", (), False),
])
def test_the_parser_reads_a_list_it_can_and_the_safety_net_asks_for_the_rest(question, options, parsed):
    got = cat.named_employer_fact(cat.build({}, HISTORY, [], company="Acme"), question, options)
    assert (got != cat.ASK_THE_USER) is parsed


@pytest.mark.parametrize("employer, question", [
    ("Initech Software", "Were you at Initech?"),                  # the history holds the subsidiary
    ("Initech Software", "Previous Initech employee?"),
    ("Initech", "Were you at Initech Software?"),                  # the history holds the parent
    ("Initech", "Previous Initech Software employee?"),
])
def test_a_parent_or_subsidiary_in_a_wording_the_parser_does_not_read_is_asked_not_no(employer, question):
    f = cat.build({}, [{"employer": employer, "title": "Engineer"}], [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    assert cat.named_employer_fact(f, question) == cat.ASK_THE_USER


@pytest.mark.parametrize("employer, question, options", [
    ("Yes Ledger", "Have you worked for Acme before?", ["Yes", "No"]),
    ("Yes Ledger", "Do you agree?", ["Yes", "No"]),
    ("Have Fun Inc", "Have you worked for Acme before?", ()),
    ("Current Widgets", "Are you a Current Employee?", ["Current Employee", "Former Employee", "Not Applicable"]),
    ("United Widgets", "Do you live in the United States?", ["United States", "Other"]),
    ("General Widgets", "Have you worked for Acme? Please select the General Employment option.", ()),
])
def test_a_common_capitalised_word_that_starts_an_employers_name_does_not_make_it_ask(employer, question, options):
    f = cat.build({}, [{"employer": employer, "title": "Engineer"}], [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    assert cat.named_employer_fact(f, question, options) is None


def test_a_stop_word_before_the_name_does_not_hide_the_parent_or_subsidiary():
    f = cat.build({}, [{"employer": "Initech Software", "title": "Engineer"}], [], company="Acme")
    assert cat.named_employer_fact(f, "Previous Initech employee?") == cat.ASK_THE_USER
    assert cat.named_employer_fact(f, "Please select: Current Initech Employee") == cat.ASK_THE_USER
    # An exact name is still found anywhere, whatever stands before it.
    f = cat.build({}, [{"employer": "Current Widgets", "title": "Engineer"}], [], company="Acme")
    assert cat.named_employer_fact(f, "Were you a Current Widgets employee?") == cat.ASK_THE_USER


@pytest.mark.parametrize("employer, question, options", [
    ("eInitech", "Did you intern at eInitech?", ()),
    ("iTech Labs", "Previous iTech employee?", ()),                 # a lowercase initial, a capital inside
    ("iTech Labs", "Which company?", ["iTech"]),
])
def test_a_brand_with_a_lowercase_initial_is_still_a_capitalised_mention(employer, question, options):
    f = cat.build({}, [{"employer": employer, "title": "Engineer"}], [], company="Acme")
    assert cat.named_employer_fact(f, question, options) == cat.ASK_THE_USER
    if not options:   # an option is read as a company whatever its case; a question's words are not
        assert cat.named_employer_fact(f, question.lower()) is None


def test_a_lowercase_word_that_is_a_history_employer_is_not_a_mention():
    """The safety net looks for a CAPITALISED whole word: "field" in "the field below" is not a company."""
    f = cat.build({}, [{"employer": "Field", "title": "Engineer"}], [], company="Acme")
    assert cat.named_employer_fact(f, "Have you worked for Acme? Give dates in the field below.") is None
    assert cat.named_employer_fact(f, "Have you worked for Acme? Give dates in the Field below.") == cat.ASK_THE_USER


@pytest.mark.parametrize("question, names", [
    ("Have you worked for Globex before?", True),
    ("Have you worked for Acme, Inc. or Globex?", True),
    ("Have you worked for any of the following companies: Globex, Umbrella?", True),
    ("Have you worked for a federal contractor?", False),
    ("Have you worked for an agency of the government?", False),
    ("Have you worked for any company in our group?", False),
    ("Have you worked for our company before?", False),
    ("Have you worked for the following: Globex?", True),
    ("Have you worked for the Federal Government?", False),
    ("Have you worked for a company with a government contract?", False),
])
def test_question_names_company_counts_only_a_capitalised_proper_name(question, names):
    assert cat.question_names_company(cat.build({}, HISTORY, [], company="Acme"), question) is names


def test_the_named_employer_is_found_past_the_catalogs_job_limit():
    jobs = [{"employer": f"Firm{i}", "title": "Engineer"} for i in range(cat.MAX_EXPERIENCE)]
    f = cat.build({}, jobs + [{"employer": "Initech", "title": "Analyst"}], [], company="Acme")
    assert f["derived.previously_employed_here"].value == "No"
    assert cat.named_employer_fact(f, "Employed by Acme or Initech?").value == "Yes, previously"


def test_only_a_derived_no_is_turned_around():
    assert cat.named_employer_fact(cat.build({}, HISTORY, [], company="Initech"), "Employed by Initech?") is None
    assert cat.named_employer_fact(cat.build({}, HISTORY, []), "Employed by Initech?") is None


def test_company_names_match_the_way_sections_match_employers():
    from app.services import autofill_sections

    assert autofill_sections.name_key is cat.name_key
    assert cat.name_key("Acme, Inc.") == cat.name_key("ACME") == "acme"


@pytest.mark.parametrize("a, b", [("The Globex Depot", "Globex Depot"), ("Globex Depot", "the globex depot, inc.")])
def test_a_leading_the_is_not_part_of_the_name(a, b):
    assert cat.name_key(a) == cat.name_key(b) == "globex depot"
    assert cat.name_key("Therion") == "therion" and cat.name_key("The") == "the"


def test_the_home_depot_in_the_history_is_the_home_depot_applied_to():
    f = cat.build({}, [{"employer": "The Globex Depot", "title": "Associate", "end_date": "2021-06"}], [],
                  company="Globex Depot")
    assert f["derived.previously_employed_here"].value == "Yes, previously"
    assert "works, or has worked," in f["derived.previously_employed_here"].describe


# ---------- languages (fill-engine plan Task 10): one entry per language,
# levels in the words forms show, native and fluent as separate Yes/No.

LANGUAGES = [
    {"language": "Spanish", "read": "Fluent", "speak": "Intermediate", "write": "Basic",
     "native": False, "fluent": True},
    {"language": "  ", "read": "Basic"},  # no language named: not an entry
    {"language": "French", "speak": "basic", "write": "", "native": "yes"},
]


def test_each_language_is_its_own_entry_of_six_facts():
    f = cat.build({"languages": LANGUAGES}, [], [])
    got = {slot: fact.value for slot, fact in f.items() if slot.startswith("languages.")}
    assert got == {
        "languages.0.language": "Spanish", "languages.0.read": "Fluent", "languages.0.speak": "Intermediate",
        "languages.0.write": "Basic", "languages.0.native": "No", "languages.0.fluent": "Yes",
        # The unnamed entry is skipped, so French is entry 2; absent levels are no facts.
        "languages.1.language": "French", "languages.1.speak": "Basic", "languages.1.native": "Yes",
    }


def test_language_facts_are_described_without_values_and_only_the_name_is_exact():
    f = cat.build({"languages": LANGUAGES}, [], [])
    assert {slot: fact.policy for slot, fact in f.items() if slot.startswith("languages.0.")} == {
        "languages.0.language": "exact", "languages.0.read": "flag", "languages.0.speak": "flag",
        "languages.0.write": "flag", "languages.0.native": "flag", "languages.0.fluent": "flag"}
    assert f["languages.0.language"].describe == "language entry 1: the language"
    assert f["languages.1.speak"].describe == "language entry 2: speaking level"
    assert f["languages.0.read"].describe == "language entry 1: reading level"
    assert f["languages.0.write"].describe == "language entry 1: writing level"
    assert f["languages.0.native"].describe == "language entry 1: a native speaker of it (yes/no)"
    assert f["languages.0.fluent"].describe == "language entry 1: fluent in it (yes/no)"
    for slot, fact in f.items():
        if slot.startswith("languages."):
            assert str(fact.value) not in fact.describe, slot


@pytest.mark.parametrize("level", ["Native", "Expert", "5", True])
def test_a_level_no_form_word_names_is_no_fact(level):
    f = cat.build({"languages": [{"language": "Spanish", "read": level, "native": "maybe"}]}, [], [])
    assert [slot for slot in f if slot.startswith("languages.")] == ["languages.0.language"]


def test_languages_are_capped_and_a_wrong_shape_builds_nothing():
    many = [{"language": f"L{i}"} for i in range(cat.MAX_LANGUAGES + 3)]
    f = cat.build({"languages": many}, [], [])
    assert sum(slot.endswith(".language") for slot in f) == cat.MAX_LANGUAGES
    for shape in ("Spanish", {"language": "Spanish"}, ["Spanish"], None):
        assert not [s for s in cat.build({"languages": shape}, [], []) if s.startswith("languages.")]


# ---------- which facts are a Yes or a No, and one description per slot (review, 2026-09-27)


def test_a_fact_whose_answer_is_a_yes_or_a_no_says_so():
    f = cat.build({**PROFILE, "eligibility": {"over_18": True}, "eeo": {"race_ethnicity": ["Asian"]},
                   "languages": [{"language": "Norwegian", "native": True, "read": "Fluent"}]},
                  EMPLOYMENT, ["Python"], company="Acme")
    yes_no = {slot for slot, fact in f.items() if fact.yes_no}
    for slot in ("work_auth.sponsorship_future", "eligibility.over_18", "derived.us_citizen",
                 "preferences.willing_to_relocate", "languages.0.native"):
        assert slot in yes_no, slot
    for slot in ("work_auth.status", "eeo.race_ethnicity", "skills", "languages.0.language", "languages.0.read",
                 "education.0.degree", "personal.city", "derived.today"):
        assert slot not in yes_no, slot


def test_every_description_comes_from_one_lookup():
    """The eval builds its facts with the same `describe_of` production uses."""
    f = cat.build({**PROFILE, "languages": [{"language": "Norwegian", "read": "Fluent"}],
                   "personal": {"first_name": "Sample", "last_name": "Person"}}, EMPLOYMENT, ["Python"])
    for slot, fact in f.items():
        if not slot.startswith("custom."):
            assert cat.describe_of(slot) == fact.describe, slot
    assert cat.describe_of("skills") == "applicant skills (a list)"
    assert cat.describe_of("languages.2.read") == "language entry 3: reading level"


# ---------- a Yes or a No however it was typed (review of 693483a5)


@pytest.mark.parametrize("typed, answer", [("yes", "Yes"), ("YES", "Yes"), ("true", "Yes"), ("Y", "Yes"),
                                           (" yes ", "Yes"), ("no", "No"), ("NO", "No"), ("false", "No"),
                                           ("n", "No"), (True, "Yes"), (False, "No")])
def test_a_stored_yes_or_no_is_one_whatever_its_case(typed, answer):
    """The panel's pause row stores eligibility answers as typed ("yes"): a
    lower-case Yes must still be a Yes or No fact, or a reversed question
    ("are you under 18?") would be asked without its meaning."""
    f = cat.build({"eligibility": {"over_18": typed}, "preferences": {"willing_to_relocate": typed}}, [], [])
    for slot in ("eligibility.over_18", "preferences.willing_to_relocate"):
        assert (f[slot].value, f[slot].yes_no) == (answer, True), slot


def test_a_yes_or_no_prefix_is_capitalised_and_other_words_are_left():
    assert cat.yes_no_word("yes, previously") == "Yes, previously"
    assert cat.yes_no_word("no, I do not") == "No, I do not"
    for word in ("Yesterday", "Norway", "N/A", "Not sure", "nope", "yes please"):
        assert cat.yes_no_word(word) == word, word
    # A name is never a Yes: a one-letter initial in the personal section stays.
    assert cat.build({"personal": {"middle_name": "Y"}}, [], [])["personal.middle_name"].value == "Y"


def test_veteran_status_reads_as_a_yes_or_no_and_still_names_its_option():
    f = cat.build({"eeo": {"veteran_status": "no"}}, [], [])["eeo.veteran_status"]
    assert (f.value, f.yes_no) == ("No, I am not a veteran", True)
    assert cat.build({"eeo": {"veteran_status": "yes"}}, [], [])["eeo.veteran_status"].value \
        == "Yes, I am a veteran"
    assert cat.build({"eeo": {"veteran_status": "decline"}}, [], [])["eeo.veteran_status"].value \
        == "I don't wish to answer"


# The words whose answer is meant as a Yes or a No: every other status word
# must not start like one, or it would be read reversed.
INTENDED_YES_NO = {("eeo.disability_status", "no"), ("eeo.disability_status", "yes"),
                   ("eeo.veteran_status", "no"), ("eeo.veteran_status", "yes"),
                   ("eeo.hispanic_latino", "yes"), ("eeo.hispanic_latino", "no")}


def test_only_the_intended_status_words_read_as_a_yes_or_no():
    got = {(slot, code) for slot, words in cat._WORDS.items() for code, text in words.items() if cat.is_yes_no(text)}
    assert got == INTENDED_YES_NO


# ---------- a Yes/No fact's description is a proposition with a direction (review of 6cd77787)

# Every slot whose answer can be a Yes or a No (a saved custom answer is
# described by its own question). Polarity judges a question against this
# description: "disability status" has no direction, "has a disability" does.
YES_NO_SLOTS = ("work_auth.authorized_now", "work_auth.sponsorship_now", "work_auth.sponsorship_future",
                "derived.sponsorship_now_or_future",
                "eligibility.over_18", "eligibility.previously_employed_here", "eligibility.non_compete",
                "eeo.hispanic_latino", "eeo.disability_status", "eeo.veteran_status", "derived.us_citizen",
                "derived.previously_employed_here", "languages.0.native", "languages.0.fluent",
                "experience.0.current", "preferences.willing_to_relocate")


def test_every_description_a_yes_or_no_fact_carries_has_a_direction():
    profile = {"work_auth": {"status": "citizen", "authorized_now": True, "sponsorship_now": False,
                             "sponsorship_future": False},
               "eligibility": {"over_18": True, "previously_employed_here": False, "non_compete": False},
               "eeo": {"hispanic_latino": "no", "disability_status": "no", "veteran_status": "no"},
               "languages": [{"language": "Norwegian", "native": True, "fluent": True}],
               "preferences": {"willing_to_relocate": True}}
    built = cat.build(profile, EMPLOYMENT, [])
    worked = cat.build(profile, EMPLOYMENT, [], company="Acme")
    for slot in YES_NO_SLOTS:
        fact = (built | worked)[slot]
        assert fact.yes_no, slot
        assert not re.search(r"\b(status|type|kind)\b", fact.describe, re.IGNORECASE), (slot, fact.describe)
    assert built["eeo.disability_status"].describe == "has a disability (voluntary self-identification)"
    assert built["eeo.veteran_status"].describe == (
        "is a veteran (voluntary self-identification; a No also settles every option that denies being a "
        "veteran or a protected veteran, and a military self-identification question whose options are "
        "protected-veteran classifications; a Yes alone never says which protected class applies, and never "
        "answers a branch, a discharge, current service or a relative's service)")
    assert built["experience.0.current"].describe == "experience entry 1: is the applicant's current job (yes/no)"


# ---------- "now or in the future": derived from the two answers the applicant gave (owner, 2026-09-27)

NOW_OR_FUTURE = "derived.sponsorship_now_or_future"


@pytest.mark.parametrize("now, later, answer", [
    (False, False, "No"), (False, True, "Yes"), (True, False, "Yes"), (True, True, "Yes"),
    ("yes", "no", "Yes"), ("NO", "no", "No"),
    (None, False, None), (False, None, None), (None, True, "Yes"), (True, None, "Yes"),
    ("maybe", False, None),
])
def test_sponsorship_now_or_in_the_future_is_derived_from_both_answers(now, later, answer):
    """Yes when either answer is Yes; No only when both are No; otherwise no fact."""
    work_auth = {k: v for k, v in (("sponsorship_now", now), ("sponsorship_future", later)) if v is not None}
    f = derived({"work_auth": work_auth})
    if answer is None:
        assert NOW_OR_FUTURE not in f
        return
    fact = f[NOW_OR_FUTURE]
    assert (fact.value, fact.yes_no, fact.policy) == (answer, True, "exact")
    assert fact.describe == ("will need visa sponsorship now or in the future "
                             "(yes/no; from the applicant's now and later answers)")


# ---------- agreeing to terms: a fact only while the agreement permission is on (live CarMax, 2026-09-30)

AGREES = "derived.agrees_to_terms"


def test_agreeing_to_terms_is_a_fact_only_with_the_agreement_permission():
    """With consent_forms on, the owner decided consent and terms ticks are
    fillable; the permission only lifted the label policy, and /map had no
    fact for a terms box. It is one now, and only while the permission is."""
    assert AGREES not in derived({}) and AGREES not in cat.with_agreement(derived({}), False)
    fact = cat.with_agreement(derived({}), True)[AGREES]
    assert (fact.value, fact.yes_no, fact.policy) == ("Yes", True, "exact")
    assert not re.search(r"\b(status|type|kind)\b", fact.describe, re.IGNORECASE)


def test_agreeing_to_terms_covers_the_applications_own_statements_and_no_optional_opt_in():
    """Owner rules (2026-09-30): background-check authorization is a consent
    the permission covers; texts, marketing, job alerts and a talent
    community are the low-stakes setting's, never this fact's."""
    described = cat.with_agreement(derived({}), True)[AGREES].describe
    assert described.startswith("agrees to the application's own terms and conditions")
    for covered in ("privacy notice", "certification", "acknowledgement", "background-check authorization"):
        assert covered in described, covered
    for never in ("texts", "marketing", "job alerts", "talent community", "willingness or circumstances",
                  "criminal history, convictions or charges", "anything a background check might find"):
        assert never in described.split("never", 1)[1], never


def test_the_agreement_fact_survives_a_catalog_at_its_cap():
    full = {f"custom.{i}": cat.make_fact(f"custom.{i}", "x", "saved answer") for i in range(cat.MAX_SLOTS)}
    got = cat.with_agreement(full, True)
    assert len(got) == cat.MAX_SLOTS and AGREES in got


# ---------- a saved answer that names a job's company or city stays with that job (Task 20c)

def test_a_saved_answer_naming_a_company_is_offered_only_for_that_company():
    profile = {"custom": [
        {"question": "Have you worked at Acme before?", "answer": "No", "only_for": "Acme", "only_for_kind": "company"},
        {"question": "Is a relative a government official?", "answer": "No"}]}
    at_acme = cat.build(profile, [], [], company="Acme Corp")
    at_globex = cat.build(profile, [], [], company="Globex")
    assert "custom.0" in at_acme and "custom.1" in at_acme
    assert "custom.0" not in at_globex and "custom.1" in at_globex
    assert "custom.0" not in cat.build(profile, [], [])          # no job: a scoped answer is never offered


def test_a_saved_answer_naming_a_city_is_offered_only_there():
    profile = {"custom": [{"question": "Willing to relocate to Austin?", "answer": "Yes", "only_for": "Austin", "only_for_kind": "city"}]}
    assert "custom.0" in cat.build(profile, [], [], company="Globex", location="Austin, TX")
    assert "custom.0" not in cat.build(profile, [], [], company="Globex", location="Denver, CO")


def test_a_scoped_saved_answer_keeps_every_other_rows_slot():
    profile = {"custom": [
        {"question": "Willing to relocate to Austin?", "answer": "Yes", "only_for": "Austin", "only_for_kind": "city"},
        {"question": "Preferred shift", "answer": "Day"}]}
    got = cat.build(profile, [], [], company="Globex", location="Denver, CO")
    assert got["custom.1"].value == "Day" and "custom.0" not in got


def test_the_context_profile_drops_a_saved_answer_that_belongs_to_another_job():
    custom = [{"question": "Have you worked at Acme before?", "answer": "No", "only_for": "Acme", "only_for_kind": "company"},
              {"question": "Preferred shift", "answer": "Day"}]
    assert [row["question"] for row in cat.custom_for_job(custom, "Acme Corp", None)] == [
        "Have you worked at Acme before?", "Preferred shift"]
    assert [row["question"] for row in cat.custom_for_job(custom, "Globex", "Austin, TX")] == ["Preferred shift"]
    assert [row["question"] for row in cat.custom_for_job(custom, None, None)] == ["Preferred shift"]


@pytest.mark.parametrize("row, company, location, offered", [
    # Whole words, not substrings.
    ({"only_for": "Crate", "only_for_kind": "company"}, "Datacrate", None, False),
    ({"only_for": "Vela", "only_for_kind": "company"}, "Velabase", None, False),
    ({"only_for": "Rome", "only_for_kind": "city"}, "Globex", "Jerome, ID", False),
    ({"only_for": "Crate", "only_for_kind": "company"}, "Crate, Inc.", None, True),
    # Which field the scope came from is the one checked.
    ({"only_for": "Phoenix", "only_for_kind": "company"}, "Globex", "Phoenix, AZ", False),
    ({"only_for": "Phoenix", "only_for_kind": "city"}, "Phoenix", "Austin, TX", False),
    ({"only_for": "Phoenix", "only_for_kind": "city"}, "Globex", "Phoenix, AZ", True),
    # A row with no kind (by hand, or from before kinds) is met by either.
    ({"only_for": "Phoenix"}, "Globex", "Phoenix, AZ", True),
    ({"only_for": "Phoenix"}, "Phoenix Labs", None, True),
    ({"only_for": "Phoenix"}, "Globex", "Austin, TX", False),
])
def test_a_scope_is_a_whole_word_in_the_field_it_came_from(row, company, location, offered):
    profile = {"custom": [{"question": "Q?", "answer": "Yes", **row}]}
    assert ("custom.0" in cat.build(profile, [], [], company=company, location=location)) is offered


# ---------- J2: the phone's country, from the profile's country

PHONE_COUNTRY_DESCRIBE = ("the phone number's country and calling code (a dialing-code picker); "
                          "never the number itself")


@pytest.mark.parametrize(("country", "expected"), [
    ("United States", "+1 United States"), ("USA", "+1 United States"), ("us", "+1 United States"),
    ("United States of America", "+1 United States"), ("Canada", "+1 Canada"),
    ("UK", "+44 United Kingdom"), ("United Kingdom", "+44 United Kingdom"), ("India", "+91 India"),
])
def test_the_phone_country_is_built_from_the_profile_country(country, expected):
    f = derived({"personal": {"country": country, "phone": "5551234567"}})
    assert f["derived.phone_country"].value == expected
    assert f["derived.phone_country"].describe == PHONE_COUNTRY_DESCRIBE
    assert f["derived.phone_country"].policy == "flag"
    assert "5551234567" not in f["derived.phone_country"].describe


@pytest.mark.parametrize("personal", [{}, {"country": " "}, {"country": "Atlantis"}, {"phone": "5551234567"}])
def test_a_phone_country_is_never_invented(personal):
    assert "derived.phone_country" not in derived({"personal": personal})


# ---------- J5: the phone's device type

def test_the_phone_type_is_mobile_when_the_profile_has_a_phone():
    f = derived({"personal": {"phone": "5551234567"}})
    assert f["derived.phone_type"].value == "Mobile"
    assert f["derived.phone_type"].describe == "the kind of phone the number is (mobile, home or work)"
    assert f["derived.phone_type"].policy == "any"


@pytest.mark.parametrize("personal", [{}, {"phone": " "}, {"city": "Springfield"}])
def test_a_phone_type_is_never_derived_without_a_phone(personal):
    assert "derived.phone_type" not in derived({"personal": personal})
