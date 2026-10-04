"""The answer receipt from the Companion's side (docs/entities/filled-answers.md). After each fill run the panel posts ONE receipt row for a matched job through the
generic `api` door (never telemetry, whatever its setting); a refused frame contributes
nothing; the flags the post returns are the Fill body's "Check before you submit"; the matched
job's knock-out verdict heads the Fill body. `runFill` is stubbed as in
test_extension_panel_fill.py's loop section."""

import json
from pathlib import Path

import pytest

from tests.extension_fixtures import entry
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    BASE_RESUMES,
    PANEL_SOURCE,
    SCORES,
    SETTINGS_REPLY,
    _armed_entry,
    _reply,
)
from tests.test_extension_panel_fill import (
    _LOOP_DRIVER_JS,
    LOOP_HOST,
    LOOP_REPORT,
    LOOP_URL,
    _answer,
    _fill,
    _field,
)

RECEIPT = "POST /api/jobs/job-lightning/filled-answers"
APP_DETAIL = {"id": "app-remembered", "status": "draft", "applied_at": None,
              "pdf_path": "renders/app-remembered/ada-resume.pdf"}
REASON = "A screening question with no saved answer behind it."
POSTED = {"id": "r1", "application_id": "app-remembered", "flag_count": 1, "flags": [
    {"index": 3, "question": "How did you hear about us?", "section": None,
     "flags": [{"id": "guessed_screening", "reason": REASON}]}]}


def _live(fid, question, committed, **extra):
    return {"fid": fid, "question": question, "section": "", "required": False, "shape": "text",
            "committed": committed, "touched": False, "multi": False, "options": None,
            "policyBlocked": False, **extra}


SKILL_OPTIONS = [{"text": text} for text in ("Python", "SQL", "Go", "Rust", "C")]
PAGE = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
    _live("v1", "First name", "Ada"),
    _live("v2", "Email", "ada@work.test", touched=True),
    _live("c1", "Highest degree", "Master's", shape="select"),
    _live("a1", "How did you hear about us?", "LinkedIn", shape="popup"),
    _live("p1", "Skills", ["Python", "SQL", "Go"], shape="search", multi=True, options=SKILL_OPTIONS),
    _live("y1", "City", "Austin", touched=True),
    _live("z1", "Pronouns", "she/her", touched=True),
    _live("s1", "Social Security Number", "000-00-0000", touched=True, policyBlocked=True),
]}}, {"frameId": 3, "result": {"frame": None, "host": "ads.example.net", "fields": []}}]
REFUSED = [{"frameId": 0, "result": {"frame": None, "host": LOOP_HOST, "fields": []}}]


def _run(tmp_path, page=PAGE, settings=SETTINGS_REPLY, match=None, **spec):
    report = spec.pop("report", LOOP_REPORT)
    spec.setdefault("tabs", [{"id": 7, "url": LOOP_URL}])
    spec.setdefault("stored", {"widget.session": entry(touched=False)})
    replies = {"read_settings": settings,
               "panel_frame0": _reply({"tier": "B", "form": True, "score": 2}),
               "panel_prepare": _reply({"injected": True}),
               "telemetry": _reply({"posted": 0}), "fill_trace": _reply({"posted": 1})}
    api = {RECEIPT: _reply(POSTED),
           "lightningai": _reply(match or {"match": "none", "job": None, "application": None}),
           "/api/base-resumes": _reply(BASE_RESUMES), "/api/ats-scores": _reply(SCORES),
           "GET /api/applications/app-remembered": _reply(APP_DETAIL)}
    frames = {"fill_inventory": page, "fill_focus": [{"frameId": 0, "result": True}],
              "fill_cancel": [{"frameId": 0, "result": True}]}
    return run_node(_LOOP_DRIVER_JS, {**spec, "report": report, "api": api, "replies": replies,
                                      "frames": frames}, tmp_path, source=PANEL_SOURCE)


def _receipts(out):
    return [msg for msg in out["sent"] if msg["type"] == "api"
            and msg["path"].endswith("/filled-answers")
            and (msg.get("init") or {}).get("method") == "POST"]


def _body(out):
    [msg] = _receipts(out)
    return json.loads(msg["init"]["body"])


def _rows(body):
    return [(field["question"], field["source"], field["edited_by_you"]) for field in body["fields"]]


def test_a_loop_run_posts_one_receipt_with_each_answers_source(tmp_path):
    assert _rows(_body(_run(tmp_path))) == [
        ("First name", "profile", False),
        ("Email", "profile", True),
        ("Highest degree", "profile", False),
        ("How did you hear about us?", "inferred", False),
        ("Skills", "resume", False),
        ("City", "you", False),
        ("Pronouns", "you", False),
    ]


def test_the_receipt_names_the_page_job_and_application(tmp_path):
    body = _body(_run(tmp_path))
    assert {key: body[key] for key in ("channel", "host", "step", "application_id")} == {
        "channel": "companion", "host": LOOP_HOST, "step": "/lightningai/jobs/99/apply",
        "application_id": "app-remembered"}


def test_the_receipt_names_the_base_resume_the_panel_knows(tmp_path):
    """Linking is by job + base: the base the fill used rides along whenever the panel
    holds one (the application's own, else the selected one)."""
    assert _body(_run(tmp_path))["base_resume"] == "ai_ml_engineer"


def test_a_field_you_changed_records_your_value_and_a_multi_select_its_list(tmp_path):
    fields = {field["question"]: field for field in _body(_run(tmp_path))["fields"]}
    assert fields["Email"]["answer"] == "ada@work.test"
    assert (fields["Skills"]["answer"], fields["Skills"]["options_count"]) == (["Python", "SQL", "Go"], 5)


def test_a_policy_blocked_field_is_never_recorded_even_when_typed(tmp_path):
    assert "000-00-0000" not in json.dumps(_body(_run(tmp_path)))


def test_a_policy_blocked_field_the_run_called_yours_is_never_recorded(tmp_path):
    """The loop reports a typed field as `yours`; if the page marks it never-fill, the
    receipt still leaves it out."""
    report = {"host": LOOP_HOST, "fields": [
        _field("s1", "Social Security Number", "yours", lastOutcome="yours"),
        _field("v1", "First name", "verified", answer="Ada", route="slot", slot="personal.first_name")]}
    body = _body(_run(tmp_path, report=report))
    assert "Social Security Number" not in [field["question"] for field in body["fields"]]
    assert "000-00-0000" not in json.dumps(body)


def test_a_refused_frame_sends_nothing(tmp_path):
    """Every frame refused the post-run read: only what the run itself reported answered
    stands, and nothing typed is read from a page that did not earn the user's data."""
    assert _rows(_body(_run(tmp_path, page=REFUSED))) == [
        ("First name", "profile", False), ("Email", "profile", False),
        ("Highest degree", "profile", False), ("How did you hear about us?", "inferred", False)]


def test_the_receipt_goes_through_the_api_door_even_with_telemetry_off(tmp_path):
    off = _reply({**SETTINGS_REPLY["data"], "telemetryEnabled": False})
    out = _run(tmp_path, settings=off)
    assert len(_receipts(out)) == 1
    assert not [msg for msg in out["sent"] if msg["type"] in ("telemetry", "fill_trace")
                and "filled-answers" in json.dumps(msg)]


def test_no_receipt_value_reaches_the_telemetry_or_the_trace(tmp_path):
    """The values the receipt carries (typed, chosen, listed) are in no telemetry or trace
    message the same run posts."""
    out = _run(tmp_path)
    assert "ada@work.test" in json.dumps(_body(out))
    value_free = [msg for msg in out["sent"] if msg["type"] in ("telemetry", "fill_trace")]
    assert value_free
    assert not [needle for needle in ("ada@work.test", "Austin", "she/her", "Master's")
                if needle in json.dumps(value_free)]


def test_no_matched_job_posts_no_receipt(tmp_path):
    assert _receipts(_run(tmp_path, stored={"widget.session": _armed_entry()})) == []


RULE_FRAMES = [{"frameId": 0, "result": {
    "filled": [
        {"label": "first name | first_name", "value": "Ada", "rule": "first-name"},
        {"label": "email | email", "value": "ada@example.test", "rule": "email"},
        {"label": "why do you want to work here? | why", "value": "The research.", "rule": "custom"},
        {"label": "skills | skills", "value": "python, pytorch", "rule": "skills"},
        {"label": "phone | phone", "value": "555", "rule": "phone",
         "note": "may not have registered, check the field"},
        {"label": "gender | gender", "value": "Female", "rule": "gender"},
    ],
    "eeoFilled": [{"field": "gender", "label": "gender | gender", "value": "Female"}],
    "corrected": [], "already": [], "seen": 6, "observations": []}}]
RULE_PAGE = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
    _live("e1", "Email", "ada@work.test", touched=True),
    _live("z1", "Pronouns", "she/her", touched=True)]}}]


def _rules(tmp_path, rules=RULE_FRAMES, page=RULE_PAGE, **spec):
    return _fill(tmp_path, start=True, stored={"widget.session": entry(touched=False)},
                 api={RECEIPT: _reply(POSTED),
                      "GET /api/applications/app-remembered": _reply(APP_DETAIL)},
                 frames={"profile_fill": rules, "fill_inventory": page}, **spec)


def test_a_rule_pass_run_posts_its_writes_with_their_rule_sources(tmp_path):
    fields = _body(_rules(tmp_path))["fields"]
    assert [(f["question"], f["source"], f["edited_by_you"], f["eeo"]) for f in fields] == [
        ("first name", "profile", False, False),
        ("Email", "profile", True, False),
        ("why do you want to work here?", "custom", False, False),
        ("skills", "resume", False, False),
        ("gender", "profile", False, True),
        ("Pronouns", "you", False, False),
    ]


def test_same_labelled_rule_writes_are_each_kept(tmp_path):
    """Latest-wins on the server is per occurrence (step, section, question, index), so two
    fields with one label are two rows here, and a change to the second one lands on it."""
    twin = [{"frameId": 0, "result": {**RULE_FRAMES[0]["result"], "eeoFilled": [], "filled": [
        {"label": "company | company", "value": "Acme", "rule": "emp-company"},
        {"label": "company | company", "value": "Initech", "rule": "emp-company"}]}}]
    page = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
        _live("c1", "Company", "Acme"), _live("c2", "Company", "Initrode", touched=True)]}}]
    fields = _body(_rules(tmp_path, rules=twin, page=page))["fields"]
    assert [(f["question"], f["answer"], f["source"], f["edited_by_you"]) for f in fields] == [
        ("company", "Acme", "resume", False), ("Company", "Initrode", "resume", True)]


def test_a_changed_field_whose_occurrence_cannot_be_told_is_its_own_row(tmp_path):
    """The page holds three "Company" fields and the pass wrote two: which write belongs to
    the changed one is unknowable, so it is a plain `you` row beside the pass's own."""
    twin = [{"frameId": 0, "result": {**RULE_FRAMES[0]["result"], "eeoFilled": [], "filled": [
        {"label": "company | company", "value": "Acme", "rule": "emp-company"},
        {"label": "company | company", "value": "Initech", "rule": "emp-company"}]}}]
    page = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
        _live("c1", "Company", "Acme"), _live("c2", "Company", "Initech"),
        _live("c3", "Company", "Hooli", touched=True)]}}]
    fields = _body(_rules(tmp_path, rules=twin, page=page))["fields"]
    assert [(f["answer"], f["source"], f["edited_by_you"]) for f in fields] == [
        ("Acme", "resume", False), ("Initech", "resume", False), ("Hooli", "you", False)]


def test_a_pause_answer_that_sticks_posts_as_yours(tmp_path):
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"},
                  stored={"widget.session": entry(touched=False)},
                  api={RECEIPT: _reply(POSTED),
                       "GET /api/applications/app-remembered": _reply(APP_DETAIL)},
                  frames={"fill_inventory": []})
    pause = json.loads(_receipts(out)[-1]["init"]["body"])["fields"]
    assert [(f["question"], f["answer"], f["source"]) for f in pause] == [
        ("how did you hear about us?", "LinkedIn", "you")]


# ---------- the source table, pure (phase 4's auto-submit rule reads it) ----------

_SOURCES_DRIVER_JS = r"""
const ns = loadModules();
emit({ slots: spec.slots.map(ns.receipt.sourceOfSlot), rules: spec.rules.map(ns.receipt.sourceOfRule) });
"""
RECEIPT_JS = (Path(__file__).resolve().parents[2] / "extension" / "shared" / "receipt.js").read_text(
    encoding="utf-8")
SLOT_SOURCES = [
    ("personal.first_name", "profile"), ("work_auth.status", "profile"),
    ("eligibility.over_18", "profile"), ("eeo.gender", "profile"),
    ("preferences.willing_to_relocate", "profile"), ("education.0.degree", "profile"),
    ("languages.0.language", "profile"), ("experience.0.title", "resume"), ("skills", "resume"),
    ("custom.3", "custom"), ("derived.full_name", "inferred"), ("derived.agrees_to_terms", "inferred"),
]
RULE_SOURCES = [
    ("first-name", "profile"), ("edu-degree", "profile"), ("work-auth", "profile"),
    ("emp-title", "resume"), ("skills", "resume"), ("custom", "custom"),
    ("consent-forms", "inferred"),
]


def test_every_slot_and_rule_maps_to_its_pill(tmp_path):
    out = run_node(_SOURCES_DRIVER_JS, {"slots": [s for s, _ in SLOT_SOURCES],
                                        "rules": [r for r, _ in RULE_SOURCES]},
                   tmp_path, source=RECEIPT_JS)
    assert out["slots"] == [source for _, source in SLOT_SOURCES]
    assert out["rules"] == [source for _, source in RULE_SOURCES]
