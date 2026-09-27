"""Task 10a: the Wording checklist, backend half.

Clichés and filler come from an editable word bank matched in CODE
(`health_wording`); spelling and grammar slips come from the classifier's
stored `language` field. All of it is a zero-score `note`, and Remove / Apply
text becomes a `suggestion` only when `health_guards` accepts it.
"""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.setting import Setting
from app.services import bullet_classify, coherence_check, health_wording
from app.services import resume_lint as rl

DEFAULT = health_wording.DEFAULT_BANK


def _lv(value, language=None, uncertain=False):
    return {"level": rl._level_name(value), "value": value, "reason": "",
            "confidence": 1.0, "source": "cache", "uncertain": uncertain,
            "language": language or []}


def _resume(bullets, summary="Data scientist with 3 years building ML systems."):
    return {
        "contact": {"email": "a@b.com"},
        "summary": summary,
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "Jan 2023", "end_date": "Present",
             "bullets": list(bullets)},
        ],
        "projects": [], "education": [], "skills": [],
    }


PASS_GATES = [
    {"id": "S1", "tier": "fatal", "status": "pass", "label": "Parse", "detail": ""},
    {"id": "S2", "tier": "fatal", "status": "pass", "label": "Contact", "detail": ""},
    {"id": "S4", "tier": "serious", "status": "pass", "label": "Headers", "detail": ""},
    {"id": "S3", "tier": "serious", "status": "pass", "label": "Dates", "detail": ""},
    {"id": "S5", "tier": "serious", "status": "pass", "label": "Placeholders", "detail": ""},
]


def _wording(notes):
    return [n for n in notes if str(n.get("rule", "")).startswith("language.")]


def _subjects(notes, rule):
    return {n["subject"] for n in notes if n.get("rule") == rule}


# --------------------------------------------------------------------------- #
# matcher + the default bank

def test_the_defaults_flag_results_driven_and_successfully():
    resume = _resume(["Successfully migrated the billing service to a new queue"],
                     summary="Results-driven engineer who ships reliable systems.")
    notes = _wording(rl.rule_notes(resume))
    assert _subjects(notes, "language.cliche") == {"results-driven"}
    assert _subjects(notes, "language.filler") == {"successfully"}
    cliche = next(n for n in notes if n["rule"] == "language.cliche")
    assert cliche["location"] == {"section": "summary"}
    assert cliche["issue"] == "'results-driven' is a cliché."
    filler = next(n for n in notes if n["rule"] == "language.filler")
    assert filler["location"] == {"section": "experience", "index": 0, "bullet_index": 0}
    assert filler["issue"] == "'successfully' adds nothing."


def test_matching_is_whole_word_and_case_insensitive():
    hits = health_wording.matches("A DYNAMIC team; very dynamically; non-dynamic; dynamic-range", DEFAULT)
    assert hits == [("cliche", "dynamic"), ("filler", "very")]


def test_one_note_per_location_and_word():
    resume = _resume(["Very very quickly shipped the very first release to customers"])
    notes = _wording(rl.rule_notes(resume))
    assert [n["subject"] for n in notes] == ["very"]


def test_a_user_added_word_flags():
    bank = health_wording.WordBank(cliche=(*DEFAULT.cliche, "rockstar"), filler=DEFAULT.filler)
    resume = _resume(["Rockstar engineer on the payments team for three years"])
    assert _subjects(rl.rule_notes(resume, word_bank=bank), "language.cliche") == {"rockstar"}
    assert not _wording(rl.rule_notes(resume))


def test_a_removed_default_stops_flagging():
    bank = health_wording.WordBank(
        cliche=DEFAULT.cliche, filler=tuple(w for w in DEFAULT.filler if w != "successfully"))
    resume = _resume(["Successfully migrated the billing service to a new queue"])
    assert _subjects(rl.rule_notes(resume), "language.filler") == {"successfully"}
    assert not _wording(rl.rule_notes(resume, word_bank=bank))


def test_never_flag_beats_the_bank():
    bank = health_wording.WordBank(cliche=DEFAULT.cliche, filler=DEFAULT.filler,
                                   ignored=("successfully",))
    resume = _resume(["Successfully migrated the billing service, a dynamic system"])
    notes = _wording(rl.rule_notes(resume, word_bank=bank))
    assert _subjects(notes, "language.filler") == set()
    assert _subjects(notes, "language.cliche") == {"dynamic"}


def test_dynamic_programming_still_flags_dynamic():
    """Known limitation (docs/health-check-rubric.md): matching is context-blind."""
    resume = _resume(["Applied dynamic programming to cut route planning time in half"])
    assert _subjects(rl.rule_notes(resume), "language.cliche") == {"dynamic"}


def test_every_scored_bullet_is_checked_but_skills_are_not():
    resume = _resume(["Built various dashboards for the sales team every quarter"])
    resume["projects"] = [{"name": "P", "bullets": ["Wrote several parsers for log files in Rust"]}]
    resume["extra_sections"] = [{"key": "vol", "title": "Volunteering", "type": "bullets",
                                 "bullets": ["Really enjoyed mentoring new volunteers each week"]}]
    resume["skills"] = [{"category": "Soft", "items": ["Team player"]}]
    notes = _wording(rl.rule_notes(resume))
    assert {(n["location"]["section"], n["subject"]) for n in notes} == {
        ("experience", "various"), ("projects", "several"), ("extra:vol", "really")}


# --------------------------------------------------------------------------- #
# Remove: one click for filler words only, and only when the result reads cleanly

NO_NOTE = "<no note>"


def _offer(text, word, bank=DEFAULT):
    """The one-click Remove text on `word`'s note for a bullet reading `text`."""
    notes = [n for n in _wording(rl.rule_notes(_resume([text]), word_bank=bank))
             if n["subject"] == word]
    return notes[0]["suggestion"] if notes else NO_NOTE


# The reviewer's probe rows (every cliché row: clichés are rewritten by hand).
CLICHE_ROWS = [
    ('Built dynamic, scalable systems for the retail team', 'dynamic'),
    ('A dynamic, detail-oriented engineer who builds data systems', 'dynamic'),
    ('Hard worker, team player, self-starter with 5 years in analytics', 'team player'),
    ('Hard worker, team player, self-starter with 5 years in analytics', 'self-starter'),
    ('Hard worker, team player, self-starter with 5 years in analytics', 'hard worker'),
    ('Proactive, results-driven engineer who ships ML systems', 'proactive'),
    ('Results-driven, detail-oriented engineer who ships ML systems', 'detail-oriented'),
    ('Results-driven, self-motivated, detail-oriented engineer who ships ML systems', 'self-motivated'),
    ('Detail-oriented and self-motivated data scientist with 5 years in retail', 'self-motivated'),
    ('Detail-oriented and self-motivated data scientist with 5 years in retail', 'detail-oriented'),
    ('Proactive and results-driven analyst who owns reporting end to end', 'results-driven'),
    ('Hard worker, team player and self-starter with 5 years in analytics', 'self-starter'),
    ('Analyst with a track record of shipping dashboards on time', 'track record'),
    ('Known as a team player on the payments team', 'team player'),
    ('Known as the go-to person for Kafka at Acme', 'go-to person'),
    ('Brought synergy to the sales and ops teams', 'synergy'),
    ('Drove synergy across three product teams', 'synergy'),
    ('A dynamic engineer who builds data systems', 'dynamic'),
    ('Served as a proactive owner of the release train', 'proactive'),
    ('Was a team player and a self-starter on the data team', 'team player'),
    ('Was a team player and a self-starter on the data team', 'self-starter'),
    ('Showed thought leadership in ML infra across the org', 'thought leadership'),
    ('Delivered value add features for the sales org', 'value add'),
    ('Is a hard worker who owns outcomes end to end', 'hard worker'),
    ('Has a proven track record in ML ops at scale', 'track record'),
    ('A self-starter who ships ML systems end to end', 'self-starter'),
    ('Self-starter who ships ML systems end to end', 'self-starter'),
    ('I think outside the box daily on hard problems', 'think outside the box'),
    ("Became the team's go-to person for Kafka and Flink", 'go-to person'),
    ('Built a best of breed ML platform for the retail team', 'best of breed'),
    ('Acted as a strategic thinker for the ML org', 'strategic thinker'),
    ('Strategic thinker with 5 years in ML ops', 'strategic thinker'),
    ('Go-getter with 5 years in ML ops at Acme', 'go-getter'),
    ('Led synergy efforts across teams at Acme', 'synergy'),
    ('Grew a self-motivated team of 5 engineers at Acme', 'self-motivated'),
    ('Grew a team of 5 self-motivated engineers at Acme', 'self-motivated'),
    ('Owned billing; was proactive about incidents', 'proactive'),
    ('Owned billing and was proactive about incidents', 'proactive'),
    ('Owned billing and was very proactive about incidents', 'proactive'),
    ('Known for being detail-oriented at Acme', 'detail-oriented'),
    ('Seen as results-oriented by the sales org', 'results-oriented'),
    ('Led efforts; results-driven', 'results-driven'),
]


@pytest.mark.parametrize("text, word", CLICHE_ROWS)
def test_a_cliche_never_gets_a_one_click_remove(text, word):
    notes = [n for n in _wording(rl.rule_notes(_resume([text]))) if n["subject"] == word]
    assert [(n["rule"], n["suggestion"]) for n in notes] == [("language.cliche", None)]
    assert notes[0]["how"] == "Rewrite this phrase in your own words, or cut it."
    assert notes[0]["issue"] == f"'{word}' is a cliché."


@pytest.mark.parametrize("text, word", [
    ("Engineer who thinks outside the box on hard problems", "think outside the box"),
    ("Built a team-player culture across the ML org", "team player"),
])
def test_an_inflected_or_hyphenated_cliche_is_not_flagged(text, word):
    """Whole-phrase matching: "thinks" and "team-player" are other words."""
    assert _offer(text, word) == NO_NOTE


def test_a_user_added_cliche_gets_no_one_click_but_a_user_added_filler_does():
    bank = health_wording.WordBank(cliche=("rockstar",), filler=("literally",))
    assert _offer("Rockstar engineer who ships billing systems", "rockstar", bank) is None
    assert _offer("Literally rebuilt the billing queue", "literally", bank) == \
        "Rebuilt the billing queue"


# The reviewer's probe rows for filler words, judged by hand: clean text or None.
FILLER_ROWS = [
    ('Led the migration successfully, then retired the old queue', 'successfully', 'Led the migration, then retired the old queue'),
    ('Shipped it efficiently, cutting cloud cost for the data team', 'efficiently', 'Shipped it, cutting cloud cost for the data team'),
    ('Migrated the service effectively, which cut latency for checkout', 'effectively', 'Migrated the service, which cut latency for checkout'),
    ('Built various, reusable dashboards for the sales team', 'various', 'Built reusable dashboards for the sales team'),
    ('Led the migration, successfully, ahead of schedule', 'successfully', 'Led the migration ahead of schedule'),
    ('Worked with various teams, vendors and partners on billing', 'various', 'Worked with teams, vendors and partners on billing'),
    ('Led sales, really, and ops for the region', 'really', None),
    ('Served as an actually useful mentor to new hires', 'actually', None),
    ('Hired a very experienced analyst for the pricing team', 'very', None),
    ('Built a very useful alerting tool for the on-call team', 'very', None),
    ('Shipped a very user-friendly dashboard for the sales team', 'very', None),
    ('Built a very hourly batch job for the finance team', 'very', None),
    ('Built a very 3-tier app for the retail team', 'very', None),
    ("Built a 'very' good parser for the log pipeline", 'very', None),
    ('"Successfully" led the rollout of the new queue', 'successfully', None),
    ('Led the migration (successfully) on time for billing', 'successfully', 'Led the migration on time for billing'),
    ('Led the migration (very successfully) on time', 'very', 'Led the migration (successfully) on time'),
    ('Shipped (via various teams) the new billing app', 'various', 'Shipped (via teams) the new billing app'),
    ('Led the very/really fast rollout of the new queue', 'very', 'Led the really fast rollout of the new queue'),
    ('Led it - successfully - on time for the finance team', 'successfully', 'Led it - on time for the finance team'),
    ('Led it — successfully — on time for the finance team', 'successfully', 'Led it — on time for the finance team'),
    ('Successfully and effectively led the billing migration', 'successfully', None),
    ('Led X; Successfully shipped the new billing queue', 'successfully', None),
    ('Very, very fast rollout of the new billing queue', 'very', 'Fast rollout of the new billing queue'),
    ('Led a very, very fast migration of the billing queue', 'very', None),
    # The guards read a capital after a newline as a name, so these two stay
    # copy-only; the newline itself survives (test_a_newline_at_the_cut_survives).
    ('Line one of the summary.\nSuccessfully led two teams', 'successfully', None),
    ('Led the team successfully... then moved to billing', 'successfully', 'Led the team... then moved to billing'),
    ('Led the team; successfully, then moved to billing', 'successfully', 'Led the team, then moved to billing'),
    ('Owned the pipeline end to end, actually.', 'actually', 'Owned the pipeline end to end.'),
    ('Owned the pipeline and basically rebuilt it', 'basically', 'Owned the pipeline and rebuilt it'),
    ('Basically rebuilt the pipeline for the finance team', 'basically', 'Rebuilt the pipeline for the finance team'),
    ('Rebuilt the pipeline, which was basically unmaintained', 'basically', None),
    ('Cut the build time by a very large margin for mobile', 'very', None),
    ('Improved a very slow, very old billing job', 'very', None),
    ('Shipped features for several teams and various customers', 'several', 'Shipped features for teams and various customers'),
    ('Shipped features for several teams and various customers', 'various', 'Shipped features for several teams and customers'),
    ('Worked across several time zones with the ML team', 'several', 'Worked across time zones with the ML team'),
    ('Reduced errors very significantly across the ingest jobs', 'very', 'Reduced errors significantly across the ingest jobs'),
    ('Wrote docs that were really, really clear for new hires', 'really', None),
    ('Led efforts that were very successful across teams', 'very', None),
    ('Delivered effectively and on time for every release', 'effectively', None),
    ('Delivered on time and effectively for every release', 'effectively', None),
    ('Delivered on time, effectively and under budget', 'effectively', None),
    ('Was actually the first to ship the new queue', 'actually', None),
    ('Did not really own the queue but fixed it anyway', 'really', None),
    ('Built tools (e.g. various parsers) for the log team', 'various', 'Built tools (e.g. parsers) for the log team'),
    ('Worked at Acme Inc. Successfully shipped the queue', 'successfully', 'Worked at Acme Inc. Shipped the queue'),
    ('One of several teams that shipped the billing queue', 'several', None),
    ('Worked on several of the ML projects at Acme', 'several', None),
    ('Worked with the various teams at Acme on billing', 'various', 'Worked with the teams at Acme on billing'),
    ('Hired a very SQL-savvy analyst for the data team', 'very', None),
    ('Built an actually MLOps-ready pipeline for Acme', 'actually', None),
    ('Led a very European rollout of the billing queue', 'very', None),
    ('Led a very one-off migration of the billing queue', 'very', None),
    ('Led an effectively honest review of the billing queue', 'effectively', None),
    ('Reduced p99 latency by 40% very quickly for checkout', 'very', 'Reduced p99 latency by 40% quickly for checkout'),
    ('Cut cost by $2M, successfully, for the billing team', 'successfully', 'Cut cost by $2M for the billing team'),
    ('Worked really hard on the billing queue at Acme', 'really', 'Worked hard on the billing queue at Acme'),
    ('Was very much involved in the billing migration', 'very', None),
    ('Delivered the very first ML model at Acme', 'very', 'Delivered the first ML model at Acme'),
    ('Owned 3 pipelines; actually rebuilt 2 of them', 'actually', 'Owned 3 pipelines; rebuilt 2 of them'),
    ('Built pipelines: very fast, very cheap', 'very', 'Built pipelines: fast, cheap'),
    ('Built pipelines — really fast ones — for billing', 'really', 'Built pipelines — fast ones — for billing'),
    ('Led the migration & successfully shipped it', 'successfully', 'Led the migration & shipped it'),
    ('Led the migration and, successfully, shipped it', 'successfully', 'Led the migration and shipped it'),
    ('Led the migration successfully and on time', 'successfully', None),
    ('Hired an efficient, reliable vendor for the data team', 'efficient', NO_NOTE),
]

# Earlier rounds' filler cases.
EARLIER_ROWS = [
    ('Successfully led the migration', 'successfully', 'Led the migration'),
    ('Successfully, led the migration', 'successfully', 'Led the migration'),
    ('successfully led the migration', 'successfully', 'led the migration'),
    ('Led the migration successfully.', 'successfully', 'Led the migration.'),
    ('Led the migration , successfully .', 'successfully', 'Led the migration.'),
    ('Built various dashboards', 'various', 'Built dashboards'),
    ('Engineer. Successfully led the migration', 'successfully', 'Engineer. Led the migration'),
    ('Very very fast', 'very', 'Fast'),
    ('Led the migration successfully\nShipped v2', 'successfully', 'Led the migration\nShipped v2'),
    ('Led the migration\nSuccessfully shipped v2', 'successfully', None),
    ('Led it very\nquickly', 'very', 'Led it\nquickly'),
    ('Kept it very/really simple', 'very', 'Kept it really simple'),
    ('Kept it really/very simple', 'very', 'Kept it really simple'),
    ('Shipped it - successfully - on time', 'successfully', 'Shipped it - on time'),
    ('Successfully - shipped it on time', 'successfully', 'Shipped it on time'),
    ('Shipped it on time - successfully', 'successfully', 'Shipped it on time'),
    ('Migrated the service effectively, which cut latency', 'effectively', 'Migrated the service, which cut latency'),
    ('Built a very useful tool', 'very', None),
    ('Hired an efficiently run team', 'efficiently', None),
]


@pytest.mark.parametrize("text, word, expected", FILLER_ROWS + EARLIER_ROWS)
def test_a_filler_remove_is_clean_or_copy_only(text, word, expected):
    assert _offer(text, word) == expected


@pytest.mark.parametrize("text, word", [
    ("Did not really own the queue", "really"),          # "not": the claim changes
    ("The queue was basically unmaintained", "basically"),  # linking verb
    ("Served as a very early adopter", "very"),           # "as" (and an article)
    ("One of several teams on billing", "several"),       # "of"
    ("Hired an actually useful vendor", "actually"),      # a/an: no article guessing
    ("Worked on several of the ML projects", "several"),  # function word next, not -ly
    ("Talked to various who owned it", "various"),        # relative pronoun next
])
def test_filler_rules_send_a_risky_cut_to_copy_only(text, word):
    assert health_wording.removal(text, word) is None


def test_an_ly_filler_before_a_function_word_is_still_offered():
    assert health_wording.removal("Shipped it successfully for the team", "successfully") == \
        "Shipped it for the team"


@pytest.mark.parametrize("text, expected", [
    ("Line one of the summary.\nSuccessfully led two teams", "Line one of the summary.\nLed two teams"),
    ("Led the migration\nSuccessfully shipped v2", "Led the migration\nShipped v2"),
])
def test_a_newline_at_the_cut_survives(text, expected):
    assert health_wording.removal(text, "successfully") == expected


def test_every_occurrence_is_cut_and_nothing_is_left_behind():
    assert health_wording.removal("very\nvery\nvery\nvery", "very") == ""
    assert "  " not in health_wording.removal("Shipped   successfully   -   on time", "successfully")


def test_remove_note_carries_a_guarded_suggestion_subject_and_hash():
    text = "Successfully led the AWS migration for the billing team"
    [note] = _wording(rl.rule_notes(_resume([text])))
    assert note["suggestion"] == "Led the AWS migration for the billing team"
    assert note["subject"] == "successfully"
    assert note["content_hash"] == bullet_classify.content_hash(text)
    assert note["type"] == "note" and note["cost"] == 0 and note["severity"] == "minor"


def test_a_filler_remove_that_drops_a_proper_noun_gets_no_suggestion():
    # "Very" capitalised mid-sentence reads as a name to the guards.
    assert _offer("Observed with the Very Large Array for the survey", "very") is None


# --------------------------------------------------------------------------- #
# slips (the classifier's `language` field)

def _assemble(resume, levels, bank=DEFAULT):
    return rl.assemble(resume, levels, PASS_GATES, "experienced", set(levels),
                       word_bank=bank)["report"]


def test_a_slip_note_swaps_the_span_for_the_fix():
    text = "Maintaned the nightly ETL jobs that feed the finance warehouse"
    resume = _resume([text])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "Maintaned", "fix": "Maintained"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["issue"] == "'Maintaned' looks like a slip: 'Maintained'."
    assert slip["suggestion"] == "Maintained the nightly ETL jobs that feed the finance warehouse"
    assert slip["subject"] == "Maintaned"
    assert slip["content_hash"] == bullet_classify.content_hash(text)
    assert slip["type"] == "note" and slip["cost"] == 0


def _slip(text, span, fix):
    report = _assemble(_resume([text]), {("experience", 0, 0): _lv(1.0, [
        {"span": span, "fix": fix}])})
    return [f for f in report["findings"] if f.get("rule") == "language.slip"]


def test_a_slip_span_that_occurs_twice_is_copy_only():
    [slip] = _slip("Ran a hour-long review of a data pipeline", "a", "an")
    assert slip["suggestion"] is None


def test_a_slip_span_inside_a_hyphenated_word_does_not_count():
    [slip] = _slip("Built in-house dashboards in a single week", "in", "within")
    assert slip["suggestion"] == "Built in-house dashboards within a single week"


def test_a_slip_span_found_only_inside_another_word_gets_no_note():
    assert _slip("Maintained the nightly ETL jobs for the finance team", "tain", "tin") == []
    assert _slip("Owned the in-house ETL jobs for the finance team", "in", "on") == []


def test_never_flag_matches_a_span_whatever_its_inner_whitespace():
    bank = health_wording.WordBank(cliche=(), filler=(), ignored=("dont  know",))
    assert health_wording.is_ignored(" Dont\t know ", bank)  # a stored legacy double space
    bank = health_wording.WordBank(cliche=(), filler=(), ignored=("dont know",))
    assert health_wording.is_ignored("Dont  know", bank)
    resume = _resume(["Said I dont  know when the vendor asked for the ETL"])
    levels = {("experience", 0, 0): _lv(1.0, [{"span": "dont  know", "fix": "don't know"}])}
    assert not [f for f in _assemble(resume, levels, bank)["findings"]
                if f.get("rule") == "language.slip"]


def test_apply_fix_is_none_unless_the_span_occurs_once():
    assert health_wording.apply_fix("a hour and a day", "a", "an") is None
    assert health_wording.apply_fix("teh cat", "teh", "the") == "the cat"
    assert health_wording.apply_fix("shipped it", "shipped it.", "x") is None


def test_slips_cover_the_summary_too():
    resume = _resume(["Owned the release train for the mobile app across teams"],
                     summary="Engineer whom ships reliable systems.")
    report = _assemble(resume, {("summary", None, None): _lv(0.5, [
        {"span": "whom", "fix": "who"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["location"] == {"section": "summary"}
    assert slip["suggestion"] == "Engineer who ships reliable systems."


def test_a_slip_fix_that_introduces_a_digit_gets_no_suggestion():
    resume = _resume(["Trained two new analysts on the reporting stack this year"])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "two", "fix": "2"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["suggestion"] is None


def test_a_slip_fix_that_drops_a_proper_noun_gets_no_suggestion():
    resume = _resume(["Moved the ingest jobs from Airflow to cron on one host"])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "from Airflow to cron", "fix": "to cron"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["suggestion"] is None


def test_never_flag_beats_a_slip_span():
    resume = _resume(["Maintaned the nightly ETL jobs that feed the finance warehouse"])
    levels = {("experience", 0, 0): _lv(1.0, [{"span": "Maintaned", "fix": "Maintained"}])}
    bank = health_wording.WordBank(cliche=DEFAULT.cliche, filler=DEFAULT.filler,
                                   ignored=("maintaned",))
    assert [f for f in _assemble(resume, levels)["findings"] if f.get("rule") == "language.slip"]
    assert not [f for f in _assemble(resume, levels, bank)["findings"]
                if f.get("rule") == "language.slip"]


# --------------------------------------------------------------------------- #
# never suppressed, never scored

def test_wording_notes_survive_a_ladder_ask_on_the_same_bullet():
    resume = _resume(["Successfully shipped it"])  # also short: bullet.too_short is suppressed
    levels = {("experience", 0, 0): _lv(0.5, [{"span": "shipped it", "fix": "shipped it."}])}
    report = _assemble(resume, levels)
    at_bullet = [f for f in report["findings"]
                 if f["location"] == {"section": "experience", "index": 0, "bullet_index": 0}]
    assert any(f["type"] == "ask" for f in at_bullet)
    rules = {f.get("rule") for f in at_bullet}
    assert {"language.filler", "language.slip"} <= rules
    assert "bullet.too_short" not in rules  # the old skip still applies to other advisories


# --------------------------------------------------------------------------- #
# storage

def test_an_absent_row_means_the_defaults(db_session):
    assert health_wording.load(db_session) == DEFAULT
    assert db_session.get(Setting, health_wording.BANK_KEY) is None


def test_save_normalizes_and_load_reads_it_back(db_session):
    health_wording.save(db_session, cliche=[" Rockstar ", "rockstar", "Ninja"],
                        filler=["very"], ignored=["Dynamic"])
    bank = health_wording.load(db_session)
    assert bank.cliche == ("rockstar", "ninja")
    assert bank.filler == ("very",)
    assert bank.ignored == ("dynamic",)


def test_reset_restores_the_defaults_but_keeps_the_ignored_list(db_session):
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=["dynamic"])
    bank = health_wording.reset(db_session)
    assert (bank.cliche, bank.filler) == (DEFAULT.cliche, DEFAULT.filler)
    assert bank.ignored == ("dynamic",)
    assert health_wording.load(db_session) == bank


def test_a_first_edit_that_loses_the_insert_race_retries_as_an_update(db_session, monkeypatch):
    from sqlalchemy import insert
    # Another request inserted both rows between our read and our commit.
    db_session.execute(insert(Setting).values(key=health_wording.BANK_KEY, value="{}"))
    db_session.execute(insert(Setting).values(key=health_wording.IGNORED_KEY, value="[]"))
    db_session.commit()
    real_get, calls = db_session.get, []

    def stale_get(model, key):
        calls.append(key)
        return None if len(calls) <= 2 else real_get(model, key)

    monkeypatch.setattr(db_session, "get", stale_get)
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=["dynamic"])
    monkeypatch.undo()
    bank = health_wording.load(db_session)
    assert (bank.cliche, bank.ignored) == (("rockstar",), ("dynamic",))
    assert len(calls) == 4  # one failed attempt, one retry


def test_a_corrupt_row_reads_as_the_defaults(db_session):
    db_session.add(Setting(key=health_wording.BANK_KEY, value="{not json"))
    db_session.add(Setting(key=health_wording.IGNORED_KEY, value='{"a": 1}'))
    db_session.commit()
    assert health_wording.load(db_session) == DEFAULT


def test_run_report_uses_the_users_bank(db_session, monkeypatch):
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=[])
    resume = _resume(["Rockstar engineer who successfully owned the payments service"])
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, data: list(PASS_GATES))
    row = rl.run_report(db_session, "base", "wording", resume, use_llm=False)
    notes = _wording(row.report_json["findings"])
    assert {n["subject"] for n in notes} == {"rockstar"}


def test_the_coherence_check_uses_the_users_bank(db_session, monkeypatch):
    monkeypatch.setattr(coherence_check.resume_lint, "structure_gates", lambda *a, **k: [])
    monkeypatch.setattr(coherence_check.llm, "call_openai", lambda **k: {"flags": []})
    monkeypatch.setattr(coherence_check.model_settings, "get_fast_model", lambda s=None: "fast")
    base = _resume(["Owned the payments service for the retail checkout team"])
    tailored = deepcopy(base)
    tailored["experience"][0]["bullets"] = ["Rockstar owner of the payments service for checkout"]

    assert not [e for e in coherence_check.run(base, tailored, db_session)["hygiene"]
                if e["rule"].startswith("language.")]
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=[])
    hygiene = coherence_check.run(base, tailored, db_session)["hygiene"]
    assert [e["rule"] for e in hygiene if e["rule"].startswith("language.")] == ["language.cliche"]


# --------------------------------------------------------------------------- #
# router

@pytest.fixture
def client(db_session):
    def _inner():
        yield db_session
    app.dependency_overrides[get_db] = _inner
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_wording_returns_the_bank_ignored_and_defaults(client):
    body = client.get("/api/resume-lint/wording").json()
    assert body == {
        "cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler), "ignored": [],
        "defaults": {"cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler)},
    }


def test_put_wording_trims_lowercases_and_dedupes(client):
    r = client.put("/api/resume-lint/wording", json={
        "cliche": [" Rockstar", "rockstar ", "Team  Player"], "filler": ["VERY"],
        "ignored": ["Dynamic", "dynamic"]})
    assert r.status_code == 200
    body = r.json()
    assert body["cliche"] == ["rockstar", "team player"]
    assert body["filler"] == ["very"]
    assert body["ignored"] == ["dynamic"]
    assert client.get("/api/resume-lint/wording").json() == body


@pytest.mark.parametrize("bad", [
    {"cliche": [""], "filler": [], "ignored": []},
    {"cliche": ["   "], "filler": [], "ignored": []},
    {"cliche": [], "filler": ["x" * 41], "ignored": []},
    {"cliche": [], "filler": [], "ignored": [f"w{i}" for i in range(201)]},
    {"cliche": [], "filler": []},
    {"cliche": [3], "filler": [], "ignored": []},
])
def test_put_wording_rejects_bad_lists_with_422(client, bad):
    r = client.put("/api/resume-lint/wording", json=bad)
    assert r.status_code == 422
    assert client.get("/api/resume-lint/wording").json()["cliche"] == list(DEFAULT.cliche)


def test_put_wording_accepts_200_entries_after_dedupe(client):
    words = [f"w{i}" for i in range(200)]
    r = client.put("/api/resume-lint/wording",
                   json={"cliche": words + ["W0"], "filler": [], "ignored": []})
    assert r.status_code == 200
    assert len(r.json()["cliche"]) == 200


def test_reset_wording_restores_defaults_and_keeps_ignored(client):
    client.put("/api/resume-lint/wording",
               json={"cliche": ["rockstar"], "filler": [], "ignored": ["dynamic"]})
    r = client.post("/api/resume-lint/wording/reset")
    assert r.status_code == 200
    assert r.json() == {
        "cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler), "ignored": ["dynamic"],
        "defaults": {"cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler)},
    }
