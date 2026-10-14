"""Resume text is the owner's own, in implied first person (Task D1).

A made-up person (Alex Rivera) with made-up companies throughout.
"""
import pytest

from app.services import resume_voice as rv

NAME = "Alex Rivera"
ORGS = ["Rivera Logistics", "Acme Corp", "Heroku Labs"]


def _kinds(text, name=NAME, orgs=ORGS):
    return [(h.kind, h.text) for h in rv.third_person_hits(text, name, orgs)]


@pytest.mark.parametrize("text, expected", [
    # third-person pronouns
    ("Led the team at Acme Corp, where he built the pipeline.", [("pronoun", "he")]),
    ("She shipped the forecasting service.", [("pronoun", "She")]),
    ("Mentored engineers so they could ship faster.", [("pronoun", "they")]),
    ("Grew his team from 3 to 9 engineers.", [("pronoun", "his")]),
    ("Raised their conversion rate by 12%.", [("pronoun", "their")]),
    ("Coached her on the migration plan.", [("pronoun", "her")]),
    ("He's built three platforms.", [("pronoun", "He")]),
    # explicit first person
    ("I built the ingestion service.", [("first_person", "I")]),
    ("Owned my team's roadmap.", [("first_person", "my")]),
    ("I've shipped four releases.", [("first_person", "I")]),
    # the contact name, in full or by token
    ("Alex Rivera led the platform rewrite.", [("name", "Alex Rivera")]),
    ("Alex built the data platform.", [("name", "Alex")]),
    ("Led the rewrite for Alex's team.", [("name", "Alex")]),
    ("Led the rewrite. Rivera shipped it.", [("name", "Rivera")]),
    # Founder ... which has/built/shipped
    ("Founder of Globex, which has shipped two products.", [("founder_which", "which has")]),
    ("Co-founder of Initech, which built a billing tool.", [("founder_which", "which built")]),
])
def test_hits(text, expected):
    got = [(h.kind, h.text) for h in rv.third_person_hits(text, NAME, ORGS) if h.blocking]
    assert got == expected


@pytest.mark.parametrize("text", [
    "Migrated services off Heroku to Kubernetes.",          # "he" inside Heroku
    "Worked with other teams on the rollout.",              # "her", "he" inside other
    "Shipped a theme system used by 40 teams.",             # "the", "them" fragments
    "Built the Thesis tracker.",
    "Scaled the Rivera Logistics routing service.",         # name inside a company
    "Cut costs at Rivera Logistics by 20%.",
    "Won a research grant and will present at a conference.",  # lower-case token words
    "Delivered Phase I and Phase II of the rollout.",       # Roman numerals
    "Studied Type I error control.",
    "Built an I/O scheduler in Rust.",
    "Led MySQL to Postgres migration.",                     # "My" inside MySQL
    "Supported HE and HR reporting.",                       # acronyms HE
    "Reduced latency by 30% across the stack.",
    "",
])
def test_not_hits(text):
    assert [h for h in rv.third_person_hits(text, NAME, ORGS) if h.blocking] == []


def test_a_leading_third_person_verb_is_flagged_not_rejected():
    hits = rv.third_person_hits("Builds data platforms. Combines ML with product sense.", NAME, ORGS)
    assert [(h.kind, h.text, h.blocking) for h in hits] == [
        ("opener", "Builds", False),
        ("opener", "Combines", False),
    ]
    assert rv.blocking(hits) == []


def test_ordinary_openers_are_not_flagged():
    for text in ("Built platforms.", "Operations lead for a 40-person team.", "Analysis of churn drove a pricing change."):
        assert rv.third_person_hits(text, NAME, ORGS) == []


def test_name_tokens_ignore_initials_and_short_tokens():
    assert rv.third_person_hits("Led Al's old team.", "Al B. Rivera", []) == []
    assert _kinds("Rivera led it.", "Al B. Rivera", []) == [("name", "Rivera")]


# --------------------------------------------------------------------------- #
# repair

@pytest.mark.parametrize("text, expected", [
    ("Led the platform team at Acme Corp, where he built the billing pipeline.",
     "Led the platform team at Acme Corp; built the billing pipeline."),
    ("Led the platform team at Acme Corp, where she has built the billing pipeline.",
     "Led the platform team at Acme Corp; built the billing pipeline."),
    ("Ran analytics for Acme Corp and they grew revenue 12%.",
     "Ran analytics for Acme Corp; grew revenue 12%."),
    ("He built the billing pipeline.", "Built the billing pipeline."),
    ("I built the billing pipeline.", "Built the billing pipeline."),
    ("Led his team of 5 engineers on the rewrite.", "Led team of 5 engineers on the rewrite."),
    ("Owned my team's roadmap for Acme Corp.", "Owned team's roadmap for Acme Corp."),
    ("Alex Rivera led the billing rewrite.", "Led the billing rewrite."),
    ("Founder of Globex, which has shipped two products.", "Founder of Globex; shipped two products."),
    ("Founder of Globex, which built a billing tool.", "Founder of Globex; built a billing tool."),
])
def test_repair_rewrites_the_clause(text, expected):
    assert rv.repair(text, NAME, ORGS) == expected


@pytest.mark.parametrize("text, expected", [
    # present tense: no tense chosen for the writer, the clause is dropped
    ("Led the platform team at Acme Corp, where he leads the billing pipeline.",
     "Led the platform team at Acme Corp."),
    ("Built the pipeline at Acme Corp, and she mentors the interns.",
     "Built the pipeline at Acme Corp."),
    # an object pronoun: drop the clause, do not guess
    ("Rolled out the new tooling, mentoring them weekly.", "Rolled out the new tooling."),
    # a headless sentence is given up, the clean one stays
    ("They are a data scientist. Built a forecasting service for Acme Corp.",
     "Built a forecasting service for Acme Corp."),
])
def test_repair_drops_what_it_cannot_fix(text, expected):
    assert rv.repair(text, NAME, ORGS) == expected


def test_repair_gives_up_when_nothing_clean_is_left():
    assert rv.repair("He is a strong leader.", NAME, ORGS) is None
    assert rv.repair("Alex Rivera is a data scientist.", NAME, ORGS) is None
    assert rv.repair("Her mentoring grew the team.", NAME, ORGS) is None


def test_repair_leaves_clean_text_alone():
    text = "Cut Heroku spend by 30% across other teams."
    assert rv.repair(text, NAME, ORGS) == text


@pytest.mark.parametrize("text", [
    "Led the platform team at Acme Corp, where he leads the pipeline, and his team grew.",
    "Alex Rivera and Alex's team built it; she shipped it, they reviewed it.",
    "He, she and they built it for Globex.",
    "Founder of Globex, which ships two products, with her partner.",
])
def test_repair_never_stores_a_pronoun_or_the_name(text):
    fixed = rv.repair(text, NAME, ORGS)
    assert fixed is None or rv.blocking(rv.third_person_hits(fixed, NAME, ORGS)) == []


# --------------------------------------------------------------------------- #
# a whole resume

def _resume(summary, bullets, name=NAME):
    return {
        "contact": {"name": name},
        "summary": summary,
        "experience": [{"company": "Rivera Logistics", "role": "Engineer", "bullets": list(bullets)}],
        "projects": [],
        "education": [],
    }


def test_changed_hits_only_looks_at_text_the_edit_wrote():
    base = _resume("Builds platforms. Alex Rivera is hands-on.", ["Led the Rivera Logistics rewrite."])
    edited = _resume(
        "Builds platforms. Alex Rivera is hands-on.",  # untouched: the edit did not write it
        ["Led the Rivera Logistics rewrite.", "Cut cost where he rebuilt the router."],
    )
    problems = rv.changed_hits(base, edited)
    assert [(p[0], p[1]) for p in problems] == [
        (("experience", 0, "bullets", 1), "Cut cost where he rebuilt the router.")
    ]


def test_repair_resume_repairs_summary_and_bullets_in_place():
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%."])
    edited = _resume(
        "Data engineer at Rivera Logistics, where she built billing.",
        ["Led the rewrite.", "Cut cost 20%, and he raised uptime to 99.9%."],
    )

    touched = rv.repair_resume(base, edited)

    assert edited["summary"] == "Data engineer at Rivera Logistics; built billing."
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]
    assert touched == [("summary",), ("experience", 0, "bullets", 1)]


def test_repair_resume_restores_the_base_line_it_cannot_repair():
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "He is great at cutting cost."])

    rv.repair_resume(base, edited)

    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%."]


def test_repair_resume_drops_a_new_bullet_it_cannot_repair():
    base = _resume("Data engineer.", ["Led the rewrite."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "She is the best."])

    rv.repair_resume(base, edited)

    assert edited["experience"][0]["bullets"] == ["Led the rewrite."]


def test_repair_resume_falls_back_to_the_base_summary():
    base = _resume("Data engineer.", ["Led the rewrite."])
    edited = _resume("Alex Rivera is a data engineer.", ["Led the rewrite."])

    rv.repair_resume(base, edited)

    assert edited["summary"] == "Data engineer."


def test_clean_resume_is_untouched():
    base = _resume("Data engineer.", ["Led the rewrite."])
    edited = _resume("Data engineer, platform focus.", ["Led the rewrite.", "Cut cost 20%."])
    assert rv.repair_resume(base, edited) == []
    assert rv.changed_hits(base, edited) == []


# --------------------------------------------------------------------------- #
# the health check advisory

def test_lint_advisory_flags_a_summary_written_about_someone_else():
    from app.services import resume_lint as rl

    resume = _resume("Alex Rivera is a data engineer who builds platforms.", ["Led the rewrite."])
    resume["experience"][0]["start_date"] = "Jan 2022"

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert len(notes) == 1
    assert notes[0]["issue"] == "This summary reads as written about someone else."
    assert notes[0]["location"] == {"section": "summary"}
    assert notes[0]["type"] == "note"


def test_lint_advisory_flags_a_bullet_and_an_opener_but_not_clean_lines():
    from app.services import resume_lint as rl

    resume = _resume(
        "Data engineer with platform focus.",
        ["Builds the routing platform for Rivera Logistics.",
         "Led a team where he cut cost 20%.",
         "Cut cost 20% at Rivera Logistics."],
    )

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert [(n["location"]["bullet_index"], n["issue"]) for n in notes] == [
        (0, "This bullet reads as written about someone else."),
        (1, "This bullet reads as written about someone else."),
    ]


def test_lint_advisory_is_silent_for_implied_first_person():
    from app.services import resume_lint as rl

    resume = _resume("Data engineer who built platforms.", ["Led the rewrite.", "Cut cost 20%."])

    assert [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"] == []
