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
    ("Alex built the data platform.", [("name_token", "Alex")]),
    ("Led the rewrite for Alex's team.", [("name_token", "Alex")]),
    ("Led the rewrite. Rivera shipped it.", [("name_token", "Rivera")]),
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
    "Rebuilt 2 of them and retired the rest.",              # "them" refers to things
    "Studied Type I error control.",
    "Built an I/O scheduler in Rust.",
    "Led MySQL to Postgres migration.",                     # "My" inside MySQL
    "Supported HE and HR reporting.",                       # acronyms HE
    "Reduced latency by 30% across the stack.",
    "",
])
def test_not_hits(text):
    assert [h for h in rv.third_person_hits(text, NAME, ORGS) if h.blocking] == []


@pytest.mark.parametrize("text, expected", [
    ("HE built data platforms.", [("pronoun", "HE")]),
    ("SHE led the rewrite.", [("pronoun", "SHE")]),
    ("MY work reduced latency 30%.", [("first_person", "MY")]),
    ("Cut cost. HE BUILT data platforms.", [("pronoun", "HE")]),   # sentence start + verb-like word
    ("THEY shipped it.", [("pronoun", "THEY")]),
])
def test_capitalised_pronouns_are_hits_when_they_read_as_a_pronoun(text, expected):
    got = [(h.kind, h.text) for h in rv.third_person_hits(text, NAME, ORGS) if h.blocking]
    assert got == expected


@pytest.mark.parametrize("text", [
    "Supported HE (Higher Education) reporting.",        # parentheses
    "Migrated the MY-SQL cluster.",                       # hyphenated
    "Supported HE and HR reporting.",                      # followed by a conjunction
    "Offices in MY and SG.",
    "Led SALES, HR AND HE REPORTING teams.",              # inside an all-caps run
    "Served the (HE) sector.",
])
def test_all_caps_acronyms_are_not_pronouns(text):
    assert [h for h in rv.third_person_hits(text, NAME, ORGS) if h.blocking] == []


def test_the_full_name_needs_word_boundaries():
    assert rv.third_person_hits("Built the Joann Leeves platform.", "Ann Lee") == []
    assert rv.repair("Built the Joann Leeves platform.", "Ann Lee") == "Built the Joann Leeves platform."
    assert [(h.kind, h.text) for h in rv.third_person_hits("Ann Lee built it.", "Ann Lee")] == [("name", "Ann Lee")]


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


def test_name_tokens_ignore_single_letter_initials():
    assert rv.third_person_hits("Led B's old team.", "A. B. Rivera", []) == []
    assert _kinds("Rivera led it.", "A. B. Rivera", []) == [("name_token", "Rivera")]


def test_two_letter_names_are_recognised_as_capitalised_words():
    hits = rv.third_person_hits("Li built data platforms.", "Li Xu")
    assert [(h.kind, h.text) for h in hits] == [("name_token", "Li")]
    assert [(h.kind, h.text) for h in rv.third_person_hits("Xu led the rewrite.", "Li Xu")] == [("name_token", "Xu")]
    assert [(h.kind, h.text) for h in rv.third_person_hits("Li Xu led the rewrite.", "Li Xu")] == [("name", "Li Xu")]
    # lower-case or all-caps are ordinary words or acronyms, not the person
    assert rv.third_person_hits("Wrote li-ion battery tests; ran LI audits.", "Li Xu") == []
    assert rv.repair("Li built data platforms.", "Li Xu") == "Built data platforms."


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
    ("Rolled out the new tooling, mentoring him weekly.", "Rolled out the new tooling."),
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


def test_changed_hits_checks_the_summary_always_and_bullets_by_location():
    base = _resume("Data engineer. Alex Rivera is hands-on.",
                   ["Led the Rivera Logistics rewrite.", "He built the router."])
    edited = _resume(
        "Data engineer. Alex Rivera is hands-on.",  # unchanged, still validated
        ["Led the Rivera Logistics rewrite.",
         "He built the router."],  # unchanged in place: not a retry reason
    )
    assert [p[0] for p in rv.changed_hits(base, edited)] == [("summary",)]

    edited["experience"][0]["bullets"][0] = "He built the router."  # base's bad line copied into a changed bullet
    edited["experience"][0]["bullets"].append("Cut cost where he rebuilt the router.")
    assert [p[0] for p in rv.changed_hits(base, edited)] == [
        ("summary",),
        ("experience", 0, "bullets", 0),
        ("experience", 0, "bullets", 2),
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


def test_repair_resume_also_repairs_an_unchanged_line_in_place():
    """Not a reason to retry (the edit did not write it), but never stored either."""
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%, and he raised uptime to 99.9%."])
    edited = _resume("Data engineer.", list(base["experience"][0]["bullets"]))

    assert rv.changed_hits(base, edited) == []
    rv.repair_resume(base, edited)

    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]


def test_a_restored_base_line_is_repaired_cleanly_or_kept_as_the_owner_wrote_it():
    # A repairable base line comes back repaired, not raw.
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%, and he raised uptime to 99.9%."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "She is a strong leader."])
    rv.repair_resume(base, edited)
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]

    # One it cannot repair cleanly is the owner's own text: kept, left to the health check.
    base = _resume("Data engineer.", ["Led the rewrite.", "He is the best at cutting cost."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "She is a strong leader."])
    rv.repair_resume(base, edited)
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "He is the best at cutting cost."]


def test_a_restored_base_summary_is_repaired_cleanly_or_kept():
    base = _resume("He built data platforms.", ["Led the rewrite."])
    edited = _resume("He is a strong leader.", ["Led the rewrite."])
    rv.repair_resume(base, edited)
    assert edited["summary"] == "Built data platforms."  # repaired, not "He built data platforms."

    base = _resume("He is a strong leader.", ["Led the rewrite."])
    edited = _resume("They are great.", ["Led the rewrite."])
    rv.repair_resume(base, edited)
    assert edited["summary"] == "He is a strong leader."  # the owner's own words stay


def test_repair_resume_is_strict_with_text_the_edit_wrote_and_gentle_with_the_base():
    base = _resume("He built it for Acme Corp. Alex Rivera leads.",
                   ["Her team grew after he left.", "Alex Rivera shipped it.", "Led the rewrite."])
    edited = _resume("They are great.",
                     ["Her team grew after he left.", "Alex Rivera shipped it.", "Led the rewrite.",
                      "I am great.", "She is great."])
    rv.repair_resume(base, edited)
    # base lines: only what repairs cleanly; "after he left" would need a clause dropped
    assert edited["experience"][0]["bullets"][:3] == [
        "Her team grew after he left.", "Shipped it.", "Led the rewrite."]
    # the edit's own lines: repaired, restored or dropped; never stored third person
    assert "I am great." not in edited["experience"][0]["bullets"]
    assert "She is great." not in edited["experience"][0]["bullets"]
    # the base summary comes back with "He built" cleaned; "Alex Rivera leads." needs a tense: kept
    assert edited["summary"] == "Built it for Acme Corp. Alex Rivera leads."


def test_unchanged_base_lines_are_never_dropped():
    lines = ["He is the best.", "Led his team and she grew it.", "Her team grew after he left."]
    base = _resume("Data engineer.", list(lines))
    edited = _resume("Data engineer.", list(lines))
    rv.repair_resume(base, edited)
    assert len(edited["experience"][0]["bullets"]) == 3
    assert edited["experience"][0]["bullets"][0] == "He is the best."
    assert edited["experience"][0]["bullets"][2] == "Her team grew after he left."


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


# --------------------------------------------------------------------------- #
# precision: a hit must be unambiguous before the text is rewritten

def _blocking(text, name=NAME, orgs=ORGS):
    return [(h.kind, h.text) for h in rv.third_person_hits(text, name, orgs) if h.blocking]


@pytest.mark.parametrize("text, name", [
    ("Built fraud models for Wells Fargo.", "Sam Wells"),
    ("Ann Arbor office lead.", "Ann Smith"),
    ("Built Central Park tooling.", "Sam Park"),
    ("Served Will County schools.", "Will Adams"),
    ("Advised Lee & Partners on pricing.", "Ann Lee"),
    ("Dr. Rivera Clinic migrated to Postgres.", "Alex Rivera"),
    ("Wrote tests for Wells.", "Sam Wells"),               # not a subject, not a possessive: flag only
    ("Reported to Rivera.", "Alex Rivera"),
])
def test_a_single_name_token_is_not_a_hit_outside_subject_or_possessive_position(text, name):
    assert _blocking(text, name, []) == []


@pytest.mark.parametrize("text, name, expected", [
    ("Wells built fraud models.", "Sam Wells", [("name_token", "Wells")]),
    ("Led it. Wells shipped billing.", "Sam Wells", [("name_token", "Wells")]),
    ("Led the team at Acme, where Wells built billing.", "Sam Wells", [("name_token", "Wells")]),
    ("Led Wells's team.", "Sam Wells", [("name_token", "Wells")]),
    ("Sam Wells led fraud models.", "Sam Wells", [("name", "Sam Wells")]),
])
def test_a_single_name_token_is_a_hit_in_subject_or_possessive_position(text, name, expected):
    assert _blocking(text, name, []) == expected


def test_a_name_beside_a_flag_only_mention_is_still_flagged_for_the_health_check():
    hits = rv.third_person_hits("Reported to Rivera.", "Alex Rivera", [])
    assert [(h.kind, h.blocking) for h in hits] == [("name_mention", False)]


def test_dr_rivera_clinic_is_left_intact_by_repair():
    text = "Dr. Rivera Clinic migrated to Postgres."
    assert rv.repair(text, "Alex Rivera", []) == text


@pytest.mark.parametrize("text", [
    "Built the HIS integration for Acme Corp.",
    "Managed HIS rollout across 40 clinics.",
    "Served the HE sector.",
    "Supported HE degrees from Acme Corp.",
    "Cut cost. Managed MY region.",
    "Led SALES, HR AND HE REPORTING teams.",
])
def test_all_caps_in_the_middle_of_a_sentence_is_an_acronym(text):
    assert _blocking(text, NAME, ORGS) == []


@pytest.mark.parametrize("text, expected", [
    ("HE built data platforms.", [("pronoun", "HE")]),
    ("HE BUILT DATA PLATFORMS.", [("pronoun", "HE")]),
    ("Cut cost. SHE led the rewrite.", [("pronoun", "SHE")]),
    ("MY work reduced latency.", [("first_person", "MY")]),
])
def test_a_shouted_pronoun_needs_a_verb_next_or_a_shouted_sentence(text, expected):
    assert _blocking(text) == expected


def test_a_company_called_her_campus_is_not_a_pronoun():
    orgs = ["Her Campus", "She Loves Data", "Rivera Logistics"]
    assert _blocking("Built tools for Her Campus.", NAME, orgs) == []
    assert _blocking("Worked with She Loves Data on dashboards.", NAME, orgs) == []
    assert _blocking("Managed My Company Inc payroll.", NAME, ["My Company Inc"]) == []
    assert rv.repair("Built tools for Her Campus.", NAME, orgs) == "Built tools for Her Campus."
    # and a real pronoun elsewhere in the same text still counts
    assert _blocking("Built tools for Her Campus, where he led QA.", NAME, orgs) == [("pronoun", "he")]


@pytest.mark.parametrize("text", [
    "Studied Annex I controls.",
    "Completed Calculus I and II.",
    "Completed Physics I, II and III.",
])
def test_roman_numerals_are_not_the_pronoun(text):
    assert _blocking(text) == []


@pytest.mark.parametrize("text, expected", [
    ("Founder of Acme, which has 2M users.", []),
    ("Founder of Acme, which serves 2M users.", []),
    ("Founder of Acme, which provides billing.", []),
    ("Founder of Acme, which helps clinics.", []),
    ("Founder of Acme, which employs 40 people.", []),
    ("Founder of Acme, which supports 3 banks.", []),
    ("Founder of Acme, which built a billing tool.", [("founder_which", "which built")]),
    ("Founder of Acme, which shipped two products.", [("founder_which", "which shipped")]),
    ("Founder of Acme, which launched in 2025.", [("founder_which", "which launched")]),
    ("Founder of Acme, which created a data lake.", [("founder_which", "which created")]),
    ("Founder of Acme, which developed an SDK.", [("founder_which", "which developed")]),
    ("Founder of Acme, which has shipped two products.", [("founder_which", "which has")]),
])
def test_founder_clauses(text, expected):
    assert _blocking(text) == expected


def test_a_soft_founder_clause_is_flagged_but_never_rewritten():
    text = "Founder of Acme, which has 2M users."
    assert [(h.kind, h.blocking) for h in rv.third_person_hits(text)] == [("founder_note", False)]
    assert rv.repair(text, NAME, ORGS) == text


@pytest.mark.parametrize("text, expected", [
    ("Platform lead (he built the billing pipeline).", "Platform lead (built the billing pipeline)."),
    ("Owned billing: she built the pipeline.", "Owned billing: built the pipeline."),
    ("Owned billing - he built the pipeline.", "Owned billing - built the pipeline."),
    ("Owned billing, where he built the pipeline.", "Owned billing; built the pipeline."),
    ("Owned billing and she built the pipeline.", "Owned billing; built the pipeline."),
    # a subordinator changes the meaning: the clause goes, nothing is joined
    ("Cut cost after he rebuilt the router, saving 20%.", "Cut cost, saving 20%."),
    ("Cut cost when she left the team.", "Cut cost."),
    ("Cut cost while they slept.", "Cut cost."),
    ("Left the team, then he built billing.", "Left the team."),
    ("Cut cost because he found the leak.", "Cut cost."),
    ("Shipped billing before she joined.", "Shipped billing."),
    ("Shipped billing since he started.", "Shipped billing."),
    ("Shipped billing, so she cut cost.", "Shipped billing."),
])
def test_joins(text, expected):
    assert rv.repair(text, NAME, ORGS) == expected


def test_a_short_line_survives_repair():
    assert rv.repair("Alex Rivera led team.", NAME, ORGS) == "Led team."


def test_ops_error_quotes_the_offending_lines():
    problems = [(("summary",), "He builds things.", []), (("experience", 0, "bullets", 1), "She led QA.", [])]
    message = rv.ops_error(problems)
    assert '"He builds things."' in message and '"She led QA."' in message
    assert "implied first person" in message


def test_paths_read_like_the_resume():
    assert rv.format_path(("summary",)) == "summary"
    assert rv.format_path(("experience", 0, "bullets", 2)) == "experience[0].bullets[2]"
    assert rv.format_path(("extra_sections", 1, "entries", 0, "bullets", 3)) == (
        "extra_sections[1].entries[0].bullets[3]")


def test_lint_flags_a_name_mention_but_not_an_employer_that_shares_a_token():
    from app.services import resume_lint as rl

    resume = _resume("Data engineer.", ["Built fraud models for Wells Fargo.", "Reported to Wells."], name="Sam Wells")
    resume["experience"][0]["company"] = "Initech"

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert [n["location"]["bullet_index"] for n in notes] == [1]  # flagged for the owner, not rewritten
    assert notes[0]["suggestion"] is None
