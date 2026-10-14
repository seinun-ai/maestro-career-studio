"""Resume text is the owner's own, in implied first person (Task D1).

A made-up person (Alex Rivera) with made-up companies throughout.

The detector is narrow on purpose: in resume bullets "they", and "he" or "she"
after a noun or a relative word, usually mean OTHER people ("the dashboard that
they used daily"). Only the shapes that are about the owner block or get
rewritten; the rest is flagged for the health check and left exactly as written.
"""
import pytest

from app.services import resume_voice as rv

NAME = "Alex Rivera"
ORGS = ["Rivera Logistics", "Acme Corp", "Heroku Labs"]


def _blocking(text, name=NAME, orgs=ORGS):
    return [(h.kind, h.text) for h in rv.third_person_hits(text, name, orgs) if h.blocking]


def _all(text, name=NAME, orgs=ORGS):
    return [(h.kind, h.text, h.blocking) for h in rv.third_person_hits(text, name, orgs)]


# --------------------------------------------------------------------------- #
# what blocks: only the five shapes that are about the owner

@pytest.mark.parametrize("text, expected", [
    # (a) a sentence- or clause-initial He/She/I + verb
    ("She shipped the forecasting service.", [("pronoun", "She")]),
    ("He's built three platforms.", [("pronoun", "He")]),
    ("Led the rewrite; he cut costs 20%.", [("pronoun", "he")]),
    ("Led the rewrite, she cut costs 20%.", [("pronoun", "she")]),
    ("Owned billing: she built the pipeline.", [("pronoun", "she")]),
    ("Led the rewrite; HE cut costs 20%.", [("pronoun", "HE")]),            # shouted, after a semicolon
    ("HE built data platforms.", [("pronoun", "HE")]),
    ("HE BUILT DATA PLATFORMS.", [("pronoun", "HE")]),
    ("Cut cost. SHE led the rewrite.", [("pronoun", "SHE")]),
    ("I built the ingestion service.", [("first_person", "I")]),
    ("I've shipped four releases.", [("first_person", "I")]),
    # (b) ", where he/she/I + verb"
    ("Led the team at Acme Corp, where he built the pipeline.", [("pronoun", "he")]),
    ("Led the team at Acme Corp, where I built the pipeline.", [("first_person", "I")]),
    # (c) a possessive that directly modifies a noun in the owner's role
    ("Grew his team from 3 to 9 engineers.", [("pronoun", "his")]),
    ("Led her team of 5 engineers.", [("pronoun", "her")]),
    ("Owned my team's roadmap.", [("first_person", "my")]),
    ("My work reduced latency 30%.", [("first_person", "My")]),
    ("MY work reduced latency 30%.", [("first_person", "MY")]),
    ("Her mentoring grew the team.", [("pronoun", "Her")]),
    # (d) the full name anywhere
    ("Alex Rivera led the platform rewrite.", [("name", "Alex Rivera")]),
    ("Led the rewrite for Alex Rivera's team.", [("name", "Alex Rivera")]),
    # (e) a given name opening a sentence or clause, then a lower-case word or a comma
    ("Alex brings 8 years of data engineering experience.", [("name_token", "Alex")]),
    ("Alex, a data engineer, built the platform.", [("name_token", "Alex")]),
    ("Led the rewrite; Alex cut costs 20%.", [("name_token", "Alex")]),
    ("Led the rewrite, Alex cut costs 20%.", [("name_token", "Alex")]),
    ("Alex built the data platform.", [("name_token", "Alex")]),
    # strict text: a bracket or a dash opens a clause too
    ("Platform lead (I led 4 engineers).", [("first_person", "I")]),
    ("Cut cost - he led the rewrite.", [("pronoun", "he")]),
    ("Cut cost \u2013 he led the rewrite.", [("pronoun", "he")]),
    ("Cut cost \u2014 she led the rewrite.", [("pronoun", "she")]),
    # auxiliaries
    ("I have built the pipeline.", [("first_person", "I")]),
    ("He has built the pipeline.", [("pronoun", "He")]),
])
def test_what_blocks(text, expected):
    assert _blocking(text) == expected


@pytest.mark.parametrize("text", [
    # they/their, or he/she after a noun or a relative word: other people
    "Built the dashboard that they used daily.",
    "Trained 40 nurses, and they adopted the EHR within a month.",
    "Wrote the model they trusted for fraud checks.",
    "Built the parser that he wrote.",
    "Founded Acme, which he grew to 40 people.",
    "Mentored engineers so they could ship faster.",
    "Raised their conversion rate by 12%.",
    "Cut cost after he rebuilt the router, saving 20%.",
    "Ran analytics for Acme Corp and she grew revenue 12%.",
    # a possessive that is not directly after the clause's verb
    "Helped a client grow his business 20%.",
    "Coached her on the migration plan.",
    # a capitalised She/He/Her/Their in mid-sentence is a proper noun
    "Presented the talk Why She Leads at the summit.",
    "Volunteered with She Codes.",
    "Spoke at Their Voice Matters.",
    # tokens
    "Migrated the my-sql cluster.",
    "Wrote my_helper tests.",
    "Migrated services off Heroku to Kubernetes.",
    "Worked with other teams on the rollout.",
    "Shipped a theme system used by 40 teams.",
    "Built the Thesis tracker.",
    "Scaled the Rivera Logistics routing service.",
    "Cut costs at Rivera Logistics by 20%.",
    "Won a research grant and will present at a conference.",
    "Rebuilt 2 of them and retired the rest.",
    "Led MySQL to Postgres migration.",
    "Reduced latency by 30% across the stack.",
    "",
])
def test_what_does_not_block(text):
    assert _blocking(text) == []


@pytest.mark.parametrize("text, expected", [
    ("Built the dashboard that they used daily.", [("pronoun_mention", "they", False)]),
    ("Built the parser that he wrote.", [("pronoun_mention", "he", False)]),
    ("Founded Acme, which he grew to 40 people.", [("pronoun_mention", "he", False)]),
    ("Raised their conversion rate by 12%.", [("pronoun_mention", "their", False)]),
    ("Presented the talk Why She Leads at the summit.", [("pronoun_mention", "She", False)]),
    ("Volunteered with She Codes.", [("pronoun_mention", "She", False)]),
    ("Helped a client grow his business 20%.", [("pronoun_mention", "his", False)]),
    # a surname, or the given name away from the start of a clause, is flagged, never blocking
    ("Led the rewrite for Alex's team.", [("name_mention", "Alex", False)]),
    ("Led the rewrite. Rivera shipped it.", [("name_mention", "Rivera", False)]),
])
def test_what_is_only_flagged(text, expected):
    assert _all(text) == expected


@pytest.mark.parametrize("text", [
    "Phase I and Phase II of the rollout.",
    "Studied Type I error control.",
    "Delivered Phase I and Phase II of the rollout.",
    "Built an I/O scheduler in Rust.",
    "Studied Annex I controls.",
    "Completed Calculus I and II.",
    "Completed Physics I, II and III.",
    "Promoted to Analyst I, then Analyst II.",
    "Hired as Engineer I at Acme Corp.",
    "Worked as Analyst I.",
])
def test_roman_numerals_are_not_the_pronoun(text):
    assert _blocking(text) == []


@pytest.mark.parametrize("text", [
    "Supported HE (Higher Education) reporting.",
    "Migrated the MY-SQL cluster.",
    "Supported HE and HR reporting.",
    "Offices in MY and SG.",
    "Led SALES, HR AND HE REPORTING teams.",
    "Served the (HE) sector.",
    "Built the HIS integration for Acme Corp.",
    "Managed HIS rollout across 40 clinics.",
    "Served the HE sector.",
    "Supported HE degrees from Acme Corp.",
    "Cut cost. Managed MY region.",
])
def test_all_caps_acronyms_are_not_pronouns(text):
    assert _all(text) == []


def test_a_company_called_her_campus_is_not_a_pronoun():
    orgs = ["Her Campus", "She Loves Data", "Rivera Logistics"]
    assert _all("Built tools for Her Campus.", NAME, orgs) == []
    assert _all("Worked with She Loves Data on dashboards.", NAME, orgs) == []
    assert _all("Managed My Company Inc payroll.", NAME, ["My Company Inc"]) == []
    # a real clause-initial pronoun elsewhere in the same text still counts
    assert _blocking("Built tools for Her Campus, he led QA.", NAME, orgs) == [("pronoun", "he")]


def test_the_full_name_needs_word_boundaries():
    assert rv.third_person_hits("Built the Joann Leeves platform.", "Ann Lee") == []
    assert [(h.kind, h.text) for h in rv.third_person_hits("Ann Lee built it.", "Ann Lee")] == [("name", "Ann Lee")]


def test_a_leading_third_person_verb_is_flagged_not_rejected():
    hits = rv.third_person_hits("Builds data platforms. Combines ML with product sense.", NAME, ORGS)
    assert [(h.kind, h.text, h.blocking) for h in hits] == [
        ("opener", "Builds", False),
        ("opener", "Combines", False),
    ]


def test_ordinary_openers_are_not_flagged():
    for text in ("Built platforms.", "Operations lead for a 40-person team.", "Analysis of churn drove a pricing change."):
        assert rv.third_person_hits(text, NAME, ORGS) == []


@pytest.mark.parametrize("text, name", [
    ("Built fraud models for Wells Fargo.", "Sam Wells"),
    ("Ann Arbor office lead.", "Ann Smith"),
    ("Built Central Park tooling.", "Sam Park"),
    ("Served Will County schools.", "Will Adams"),
    ("Advised Lee & Partners on pricing.", "Ann Lee"),
    ("Dr. Rivera Clinic migrated to Postgres.", "Alex Rivera"),
    ("Wrote tests for Wells.", "Sam Wells"),
    ("Reported to Rivera.", "Alex Rivera"),
    ("Led Priya, Alex and Sam on the rewrite.", "Alex Rivera"),     # a list of names
    ("Led Priya, Alex, and Sam on the rewrite.", "Alex Rivera"),
    ("Thanked Alex for the review.", "Alex Rivera"),
])
def test_a_name_token_that_is_not_the_owner_acting_is_not_a_hit(text, name):
    assert _blocking(text, name, []) == []


@pytest.mark.parametrize("text, name", [
    ("Shah built the router.", "Ravi Shah"),
    ("Ford's EV team adopted the tool.", "Chris Ford"),
    ("Wells built fraud models.", "Sam Wells"),
    ("Led the team at Acme, where Wells built billing.", "Sam Wells"),
    ("Led Wells's team.", "Sam Wells"),
])
def test_a_surname_is_flagged_never_blocking(text, name):
    hits = rv.third_person_hits(text, name, [])
    assert [(h.kind, h.blocking) for h in hits] == [("name_mention", False)]
    assert rv.repair(text, name, []) == text


@pytest.mark.parametrize("text", [
    "Austin, TX office lead.",
    "Austin, Texas office lead.",
    "Austin Texas office lead.",
])
def test_a_given_name_that_is_a_place_is_not_a_hit(text):
    assert _blocking(text, "Austin Reed", []) == []


def test_a_given_name_that_is_an_appositive_subject_still_blocks():
    assert _blocking("Austin, a data engineer, built the platform.", "Austin Reed", []) == [("name_token", "Austin")]


def test_name_tokens_ignore_single_letter_initials():
    assert rv.third_person_hits("Led B's old team.", "A. B. Rivera", []) == []
    # with one real token left, it is the given name
    assert _blocking("Rivera led it.", "A. B. Rivera", []) == [("name_token", "Rivera")]


def test_two_letter_names_are_recognised_as_capitalised_words():
    assert _blocking("Li built data platforms.", "Li Xu", []) == [("name_token", "Li")]
    assert _blocking("Xu led the rewrite.", "Li Xu", []) == []
    assert _blocking("Li Xu led the rewrite.", "Li Xu", []) == [("name", "Li Xu")]
    assert rv.third_person_hits("Wrote li-ion battery tests; ran LI audits.", "Li Xu") == []
    assert rv.repair("Li built data platforms.", "Li Xu") == "Built data platforms."


@pytest.mark.parametrize("text, expected", [
    ("Founder of Acme, which has 2M users.", []),
    ("Founder of Acme, which serves 2M users.", []),
    ("Founder of Acme, which built a billing tool.", []),
    ("Founder of Acme, which has shipped two products.", []),
])
def test_founder_clauses_never_block(text, expected):
    assert _blocking(text) == expected


def test_a_founder_clause_is_flagged_but_never_rewritten():
    for text in ("Founder of Acme, which has 2M users.", "Founder of Globex, which has shipped two products."):
        assert [(h.kind, h.blocking) for h in rv.third_person_hits(text)] == [("founder_note", False)]
        assert rv.repair(text, NAME, ORGS) == text


# --------------------------------------------------------------------------- #
# repair: the only rewrites allowed

@pytest.mark.parametrize("text, expected", [
    ("He built the billing pipeline.", "Built the billing pipeline."),
    ("I built the billing pipeline.", "Built the billing pipeline."),
    ("Led the platform team at Acme Corp, where he built the billing pipeline.",
     "Led the platform team at Acme Corp; built the billing pipeline."),
    ("Led the platform team at Acme Corp, where I built the billing pipeline.",
     "Led the platform team at Acme Corp; built the billing pipeline."),
    ("I have built the billing pipeline.", "Built the billing pipeline."),
    ("I've built the billing pipeline.", "Built the billing pipeline."),
    ("He's built the billing pipeline.", "Built the billing pipeline."),
    ("He has built the billing pipeline.", "Built the billing pipeline."),
    ("Led the team at Acme Corp, where she has built the billing pipeline.",
     "Led the team at Acme Corp; built the billing pipeline."),
    ("Led his team of 5 engineers on the rewrite.", "Led team of 5 engineers on the rewrite."),
    ("Owned my team's roadmap for Acme Corp.", "Owned team's roadmap for Acme Corp."),
    ("Alex Rivera led the billing rewrite.", "Led the billing rewrite."),
    ("Alex built the billing pipeline.", "Built the billing pipeline."),
    ("Led the rewrite; Alex cut costs 20%.", "Led the rewrite; cut costs 20%."),
    ("Alex Rivera led team.", "Led team."),
])
def test_repair_rewrites(text, expected):
    assert rv.repair(text, NAME, ORGS) == expected
    assert rv.repair(text, NAME, ORGS, conservative=True) == expected  # the same fixes in both modes


@pytest.mark.parametrize("text, expected", [
    ("Owned billing: she built the pipeline.", "Owned billing: built the pipeline."),
    ("Led the rewrite; HE cut costs 20%.", "Led the rewrite; cut costs 20%."),
    ("Led the rewrite; he has built billing.", "Led the rewrite; built billing."),
    ("Platform lead (I led 4 engineers).", "Platform lead (led 4 engineers)."),
    ("Cut cost - he led the rewrite.", "Cut cost - led the rewrite."),
    ("Cut cost \u2013 he led the rewrite.", "Cut cost \u2013 led the rewrite."),
    ("Cut cost \u2014 she led the rewrite.", "Cut cost \u2014 led the rewrite."),
])
def test_strict_repair_also_fixes_a_clause_after_a_bracket_dash_semicolon_or_colon(text, expected):
    assert rv.repair(text, NAME, ORGS) == expected


@pytest.mark.parametrize("text", [
    "Mentored a new hire; she shipped her first feature in 2 weeks.",
    "Hired Marco as lead; he built the data team to 12.",
    "Onboarded the CFO: she approved the budget.",
    "Mentored Priya; doubled her output.",
    "Mentored Priya, doubled her output.",
    "Platform lead (I led 4 engineers).",
    "Cut cost - he led the rewrite.",
])
def test_a_base_line_is_only_touched_when_he_she_or_i_starts_a_sentence(text):
    """On the owner's own line, a he/she after ; : , is usually someone else, and a possessive
    after another person is theirs: flagged for the health check, never rewritten."""
    assert rv.repair(text, NAME, ORGS, conservative=True) == text
    assert rv.blocking(rv.third_person_hits(text, NAME, ORGS, base_line=True)) == []
    assert rv.third_person_hits(text, NAME, ORGS, base_line=True)  # but the advisory still sees it


def test_a_shouted_clause_after_a_semicolon_is_left_alone_on_a_base_line():
    text = "Led the rewrite; HE cut costs 20%."
    assert rv.repair(text, NAME, ORGS, conservative=True) == text
    assert rv.blocking(rv.third_person_hits(text, NAME, ORGS, base_line=True)) == []


def test_the_same_text_from_the_model_is_strict():
    text = "Mentored a new hire; she shipped her first feature in 2 weeks."
    assert rv.blocking(rv.third_person_hits(text, NAME, ORGS))
    assert rv.repair(text, NAME, ORGS) != text


def test_a_base_line_with_a_sentence_initial_pronoun_or_a_first_clause_possessive_is_still_repaired():
    assert rv.repair("He built billing. Cut cost.", NAME, ORGS, conservative=True) == "Built billing. Cut cost."
    assert rv.repair("Led his team of 5.", NAME, ORGS, conservative=True) == "Led team of 5."


@pytest.mark.parametrize("text", [
    "Alex brings 8 years of data engineering experience.",          # present tense: not mechanical
    "Alex, a data engineer, built the platform.",
    "He builds billing for Acme Corp.",
    "Led the team at Acme Corp, where he leads the billing pipeline.",
    "Her mentoring grew the team.",
    "He is a strong leader.",
    "Alex Rivera is a data scientist.",
])
def test_what_is_not_mechanical_is_not_rewritten_in_conservative_mode(text):
    assert rv.repair(text, NAME, ORGS, conservative=True) == text


def test_strict_repair_drops_only_the_sentences_it_cannot_fix():
    assert rv.repair("Cut cost. He is great. Shipped billing.", NAME, ORGS) == "Cut cost. Shipped billing."
    assert rv.repair("She is a data scientist. Built a forecasting service for Acme Corp.", NAME, ORGS) == (
        "Built a forecasting service for Acme Corp.")


@pytest.mark.parametrize("text", [
    "He is a strong leader.",
    "Alex Rivera is a data scientist.",
    "Alex brings 8 years of experience.",
    "Her mentoring grew the team.",
    "Led the team at Acme Corp, where she is building billing.",
])
def test_strict_repair_gives_up_when_nothing_clean_is_left(text):
    assert rv.repair(text, NAME, ORGS) is None


@pytest.mark.parametrize("text", [
    "Built the dashboard that they used daily.",
    "Trained 40 nurses, and they adopted the EHR within a month.",
    "Wrote the model they trusted for fraud checks.",
    "Built the parser that he wrote.",
    "Helped a client grow his business 20%.",
    "Presented Why She Leads at the summit.",
    "Cut cost after he rebuilt the router, saving 20%.",
    "Dr. Rivera Clinic migrated to Postgres.",
    "Cut Heroku spend by 30% across other teams.",
])
def test_text_about_other_people_is_never_touched_in_either_mode(text):
    assert rv.repair(text, NAME, ORGS) == text
    assert rv.repair(text, NAME, ORGS, conservative=True) == text


@pytest.mark.parametrize("text", [
    "Led the platform team, where he leads the pipeline, and his team grew.",
    "Alex Rivera and Alex's team built it; she shipped it, they reviewed it.",
    "He, she and they built it for Globex.",
    "Led the rewrite; Alex brings experience; I built it.",
])
def test_repair_never_stores_a_blocking_hit(text):
    fixed = rv.repair(text, NAME, ORGS)
    assert fixed is None or rv.blocking(rv.third_person_hits(fixed, NAME, ORGS)) == []


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
    edited["experience"][0]["bullets"].append("Cut cost, where he rebuilt the router.")
    assert [p[0] for p in rv.changed_hits(base, edited)] == [
        ("summary",),
        ("experience", 0, "bullets", 0),
        ("experience", 0, "bullets", 2),
    ]


def test_repair_resume_repairs_summary_and_bullets_in_place():
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%."])
    edited = _resume(
        "Data engineer at Rivera Logistics, where she built billing.",
        ["Led the rewrite.", "Cut cost 20%, where he raised uptime to 99.9%."],
    )

    touched = rv.repair_resume(base, edited)

    assert edited["summary"] == "Data engineer at Rivera Logistics; built billing."
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]
    assert touched == [("summary",), ("experience", 0, "bullets", 1)]


def test_repair_resume_also_repairs_an_unchanged_line_in_place():
    """Not a reason to retry (the edit did not write it), but repaired where that is mechanical."""
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%, where he raised uptime to 99.9%."])
    edited = _resume("Data engineer.", list(base["experience"][0]["bullets"]))

    assert rv.changed_hits(base, edited) == []
    rv.repair_resume(base, edited)

    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]


def test_unchanged_lines_about_other_people_are_stored_byte_for_byte():
    lines = ["Built the dashboard that they used daily.",
             "Trained 40 nurses, and they adopted the EHR within a month.",
             "Wrote the model they trusted for fraud checks."]
    base = _resume("Data engineer who built what they asked for.", list(lines))
    edited = _resume("Data engineer who built what they asked for.", list(lines))

    assert rv.repair_resume(base, edited) == []
    assert edited["experience"][0]["bullets"] == lines
    assert edited["summary"] == base["summary"]


def test_a_restored_base_line_is_repaired_cleanly_or_kept_as_the_owner_wrote_it():
    base = _resume("Data engineer.", ["Led the rewrite.", "Cut cost 20%, where he raised uptime to 99.9%."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "She is a strong leader."])
    rv.repair_resume(base, edited)
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "Cut cost 20%; raised uptime to 99.9%."]

    base = _resume("Data engineer.", ["Led the rewrite.", "He is the best at cutting cost."])
    edited = _resume("Data engineer.", ["Led the rewrite.", "She is a strong leader."])
    rv.repair_resume(base, edited)
    assert edited["experience"][0]["bullets"] == ["Led the rewrite.", "He is the best at cutting cost."]


def test_a_restored_base_summary_is_repaired_cleanly_or_kept():
    base = _resume("He built data platforms.", ["Led the rewrite."])
    edited = _resume("He is a strong leader.", ["Led the rewrite."])
    rv.repair_resume(base, edited)
    assert edited["summary"] == "Built data platforms."

    base = _resume("He is a strong leader.", ["Led the rewrite."])
    edited = _resume("She is great.", ["Led the rewrite."])
    rv.repair_resume(base, edited)
    assert edited["summary"] == "He is a strong leader."  # the owner's own words stay


def test_repair_resume_is_strict_with_text_the_edit_wrote_and_gentle_with_the_base():
    base = _resume("He built it for Acme Corp. Alex Rivera leads.",
                   ["Her team grew after he left.", "Alex Rivera shipped it.", "Led the rewrite."])
    edited = _resume("She is great.",
                     ["Her team grew after he left.", "Alex Rivera shipped it.", "Led the rewrite.",
                      "I am great.", "She is great."])
    rv.repair_resume(base, edited)
    # base lines: only what repairs mechanically; "Her team grew" would need a rewrite
    assert edited["experience"][0]["bullets"][:3] == [
        "Her team grew after he left.", "Shipped it.", "Led the rewrite."]
    # the edit's own lines: repaired, restored or dropped; never stored third person
    assert "I am great." not in edited["experience"][0]["bullets"]
    assert "She is great." not in edited["experience"][0]["bullets"]
    assert edited["summary"] == "Built it for Acme Corp. Alex Rivera leads."


def test_unchanged_base_lines_are_never_dropped():
    lines = ["He is the best.", "Led his team and she grew it.", "Her team grew after he left."]
    base = _resume("Data engineer.", list(lines))
    edited = _resume("Data engineer.", list(lines))
    rv.repair_resume(base, edited)
    assert len(edited["experience"][0]["bullets"]) == 3
    assert edited["experience"][0]["bullets"][0] == "He is the best."
    assert edited["experience"][0]["bullets"][1] == "Led team and she grew it."
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
         "Led a team, where he cut cost 20%.",
         "Cut cost 20% at Rivera Logistics."],
    )

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert [(n["location"]["bullet_index"], n["issue"]) for n in notes] == [
        (0, "This bullet reads as written about someone else."),
        (1, "This bullet reads as written about someone else."),
    ]


def test_lint_advisory_flags_an_ambiguous_they_but_offers_no_rewrite():
    from app.services import resume_lint as rl

    resume = _resume("Data engineer.", ["Built the dashboard that they used daily."])

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert len(notes) == 1 and notes[0]["suggestion"] is None


def test_lint_advisory_is_silent_for_implied_first_person():
    from app.services import resume_lint as rl

    resume = _resume("Data engineer who built platforms.", ["Led the rewrite.", "Cut cost 20%."])

    assert [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"] == []


def test_lint_flags_a_name_mention_but_not_an_employer_that_shares_a_token():
    from app.services import resume_lint as rl

    resume = _resume("Data engineer.", ["Built fraud models for Wells Fargo.", "Reported to Wells."], name="Sam Wells")
    resume["experience"][0]["company"] = "Initech"

    notes = [n for n in rl.rule_notes(resume) if n["rule"] == "voice.third_person"]

    assert [n["location"]["bullet_index"] for n in notes] == [1]  # flagged for the owner, not rewritten
    assert notes[0]["suggestion"] is None
