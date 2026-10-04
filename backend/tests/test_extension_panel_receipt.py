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


def _run(tmp_path, page=PAGE, settings=SETTINGS_REPLY, match=None, api_extra=None, **spec):
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
           "GET /api/applications/app-remembered": _reply(APP_DETAIL), **(api_extra or {})}
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


def _item(fid, rule, value="x"):
    return {"label": "what the rule matched on", "value": value, "rule": rule, "fid": fid}


def _group(fid, question, committed, options, **extra):
    return _live(fid, question, committed, shape="group", multi=isinstance(committed, list),
                 options=[{"text": text} for text in options], **extra)


RULE_FRAMES = [{"frameId": 0, "result": {
    "filled": [
        _item("v1", "first-name"),
        _item("v2", "email"),
        _item("w1", "work-auth"),
        _item("why", "custom"),
        _item("sk", "skills"),
        _item("r1", "race-ethnicity"),
        _item("r1", "race-ethnicity"),
        _item("ph", "phone"),
        _item("sg", "initials"),
        {"label": "orphan", "value": "z", "rule": "city"},
    ],
    "corrected": [], "already": [], "seen": 6, "observations": []}}]
RACES = ["Asian", "White", "Black or African American"]
RULE_PAGE = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
    _live("v1", "First name", "Ada"),
    _live("v2", "Email", "ada@work.test", touched=True),
    _group("w1", "Are you authorized to work in the US?", "Yes", ["Yes", "No"]),
    _live("why", "Why do you want to work here?", "The research.", shape="textarea"),
    _live("sk", "Skills", ["python", "pytorch"], shape="search", multi=True, options=SKILL_OPTIONS),
    _group("r1", "Race (select all that apply)", ["Asian"], RACES),
    _live("ph", "Phone", ""),
    _live("z1", "Pronouns", "she/her", touched=True),
    _live("sg", "Initials", "AD", policyBlocked=True),
]}}]


def _rules(tmp_path, rules=RULE_FRAMES, page=RULE_PAGE, api_extra=None, **spec):
    return _fill(tmp_path, start=True, stored={"widget.session": entry(touched=False)},
                 api={RECEIPT: _reply(POSTED),
                      "GET /api/applications/app-remembered": _reply(APP_DETAIL), **(api_extra or {})},
                 frames={"profile_fill": rules, "fill_inventory": page}, **spec)


def _rule_fields(tmp_path, **spec):
    return {f["question"]: f for f in _body(_rules(tmp_path, **spec))["fields"]}


def test_a_rule_pass_run_posts_each_field_the_inventory_names(tmp_path):
    """The rows are the PAGE's fields (their question, value and options), found by the fid the
    rule pass named: never the label a rule matched on, which for a radio is the option."""
    fields = _body(_rules(tmp_path))["fields"]
    assert [(f["question"], f["answer"], f["source"], f["edited_by_you"], f["eeo"]) for f in fields] == [
        ("First name", "Ada", "profile", False, False),
        ("Email", "ada@work.test", "profile", True, False),
        ("Are you authorized to work in the US?", "Yes", "profile", False, False),
        ("Why do you want to work here?", "The research.", "custom", False, False),
        ("Skills", ["python", "pytorch"], "resume", False, False),
        ("Race (select all that apply)", ["Asian"], "profile", False, True),
        ("Pronouns", "she/her", "you", False, False),
    ]


def test_a_checkbox_group_is_one_row_with_a_list_and_its_option_count(tmp_path):
    fields = _rule_fields(tmp_path)
    race = fields["Race (select all that apply)"]
    assert (race["answer"], race["options_count"], race["slot"]) == (["Asian"], 3, "eeo.race_ethnicity")
    assert fields["Are you authorized to work in the US?"]["options_count"] is None


def test_a_rule_write_the_page_does_not_hold_is_not_recorded(tmp_path):
    """No field behind it (no fid), an empty value (it did not register) or a field no frame
    answered about: nothing is guessed from the label."""
    questions = " ".join(_rule_fields(tmp_path))
    assert "orphan" not in questions and "Phone" not in questions
    assert _receipts(_rules(tmp_path, page=REFUSED)) == []


def test_a_never_fill_field_is_not_recorded_on_the_rule_pass(tmp_path):
    assert "Initials" not in _rule_fields(tmp_path)
    assert "AD" not in json.dumps(_body(_rules(tmp_path)))


def test_same_labelled_rule_writes_are_each_kept_in_page_order(tmp_path):
    """Latest-wins on the server is per occurrence (step, section, question, index): two
    fields with one label are two rows, in the page's order, and a change to the second one
    lands on the second."""
    twin = [{"frameId": 0, "result": {**RULE_FRAMES[0]["result"], "filled": [
        _item("c2", "emp-company"), _item("c1", "emp-company")]}}]
    page = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
        _live("c1", "Company", "Acme"), _live("c2", "Company", "Initrode", touched=True)]}}]
    fields = _body(_rules(tmp_path, rules=twin, page=page))["fields"]
    assert [(f["answer"], f["source"], f["edited_by_you"]) for f in fields] == [
        ("Acme", "resume", False), ("Initrode", "resume", True)]


def test_a_label_with_an_asterisk_is_the_inventorys_question(tmp_path):
    page = [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": [
        _live("v1", "First name", "Ada")]}}]
    rules = [{"frameId": 0, "result": {**RULE_FRAMES[0]["result"], "filled": [
        {"label": "first name * | first_name", "value": "Ada", "rule": "first-name", "fid": "v1"}]}}]
    assert [f["question"] for f in _body(_rules(tmp_path, rules=rules, page=page))["fields"]] == ["First name"]


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
    # The profile's own first and last name joined: a saved fact, like the rule `full-name`.
    ("custom.3", "custom"), ("derived.full_name", "profile"), ("derived.agrees_to_terms", "inferred"),
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


# ---------- one policy, bounds the server enforces, the run's consent ----------

def _page(*fields):
    return [{"frameId": 0, "result": {"frame": "f0", "host": LOOP_HOST, "fields": list(fields)}}]


def test_a_never_fill_field_is_not_recorded_on_the_loop_path_either(tmp_path):
    """The loop reports the field as written; the page says the policy never fills it."""
    page = _page(_live("v1", "First name", "Ada", policyBlocked=True),
                 _live("v2", "Email", "ada@work.test"))
    questions = [f["question"] for f in _body(_run(tmp_path, page=page))["fields"]]
    assert "First name" not in questions and "Email" in questions


@pytest.mark.parametrize("consent", [True, False])
def test_the_post_run_read_carries_the_runs_consent_and_starts_no_run(tmp_path, consent):
    """A consent tick made under standing consent is never-fill only without it, so the
    page is read under the run's own consent; `readOnly` leaves the engine's alone."""
    out = _run(tmp_path, report={**LOOP_REPORT, "consentForms": consent})
    reads = [msg["message"] for msg in out["broadcasts"] if msg["message"]["type"] == "fill_inventory"
             and msg["message"].get("readOnly")]
    assert [(read["consentForms"], "runId" in read) for read in reads] == [(consent, False)]


def test_the_rule_pass_read_carries_the_standing_consent_of_its_context(tmp_path):
    context = {"profile": {"first_name": "Ada"}, "employment": [], "skills": [],
               "eeo_consent": {"enabled": False, "consent_forms": True,
                               "acknowledged_at": None, "policy_version": ""}}
    out = _rules(tmp_path, api_extra={"/api/autofill/context": _reply(context)})
    [read] = [msg["message"] for msg in out["sent"] if msg["type"] == "page_broadcast"
              and msg["message"].get("readOnly")]
    assert read["consentForms"] is True


def test_a_field_that_would_break_the_servers_bounds_is_cut_not_sent_whole(tmp_path):
    """One oversize or label-less field must not cost the whole run its record (a 422)."""
    page = _page(
        _live("v1", "First name", "Ada"),
        _live("q1", "Q" * 600, "A" * 25000, touched=True),
        _live("q2", "   ", "nameless", touched=True),
        _live("p1", "Skills", ["Python"] * 150, shape="search", multi=True,
              options=[{"text": str(i)} for i in range(1500)]),
    )
    fields = {f["question"][:3]: f for f in _body(_run(tmp_path, page=page))["fields"]}
    assert len(fields["QQQ"]["question"]) == 500 and len(fields["QQQ"]["answer"]) == 20000
    assert fields["Ski"]["options_count"] == 1000 and len(fields["Ski"]["answer"]) == 100
    assert "nameless" not in json.dumps(_body(_run(tmp_path, page=page)))


def test_a_failed_post_logs_the_status_and_never_the_message(tmp_path):
    out = _run(tmp_path, api_extra={RECEIPT: {"ok": False, "error": "secret-body-text", "status": 422}})
    logged = [line for line in out["warnings"] if "answer record" in line]
    assert logged and "secret-body-text" not in " ".join(logged) and "422" in logged[0]


# ---------- what you changed after the run: Mark applied, and leaving the page ----------

EDITED = _page(
    _live("v1", "First name", "Adaline", touched=True),
    _live("v2", "Email", "ada@work.test", touched=True),
    _live("c1", "Highest degree", "Master's", shape="select"),
    _live("a1", "How did you hear about us?", "LinkedIn", shape="popup"),
    _live("p1", "Skills", ["Python", "SQL", "Go"], shape="search", multi=True, options=SKILL_OPTIONS),
    _live("y1", "City", "Austin", touched=True),
    _live("z1", "Pronouns", "she/her", touched=True),
    _live("s1", "Social Security Number", "000-00-0000", touched=True, policyBlocked=True),
)
APPLIED = {"PATCH /api/applications/app-remembered": _reply({**APP_DETAIL, "status": "applied",
                                                             "applied_at": "2026-10-04T10:00:00+00:00"})}
TABS = [{"id": 7, "url": LOOP_URL}, {"id": 8, "url": "https://example.com/elsewhere"}]


def _second(out):
    receipts = _receipts(out)
    assert len(receipts) == 2, [msg["path"] for msg in receipts]
    return json.loads(receipts[1]["init"]["body"])


def test_an_edit_after_the_fill_is_posted_at_mark_applied_before_the_status_moves(tmp_path):
    out = _run(tmp_path, pressStatus="Applied", framesAfter={"fill_inventory": EDITED}, api_extra=APPLIED)
    body = _second(out)
    fields = {f["question"]: f for f in body["fields"]}
    # Your edit of a run's write keeps the run's source and says it is edited; the rest
    # of what was posted is restated, so the server's per-occurrence order holds.
    assert (fields["First name"]["answer"], fields["First name"]["source"],
            fields["First name"]["edited_by_you"]) == ("Adaline", "profile", True)
    assert (fields["City"]["source"], fields["City"]["edited_by_you"]) == ("you", False)
    assert "Social Security Number" not in fields
    # The two receipts, then the status PATCH: the page is read while it is still the form.
    kinds = [msg["init"]["method"] for msg in out["sent"] if msg["type"] == "api"
             and msg.get("init", {}).get("method") in ("POST", "PATCH")
             and (msg["path"].endswith("/filled-answers") or msg["init"]["method"] == "PATCH")]
    assert kinds == ["POST", "POST", "PATCH"]


def test_nothing_changed_since_the_post_posts_nothing_at_mark_applied(tmp_path):
    out = _run(tmp_path, pressStatus="Applied", api_extra=APPLIED)
    assert len(_receipts(out)) == 1


def test_leaving_the_page_posts_the_pending_edits_once(tmp_path):
    out = _run(tmp_path, tabs=TABS, leaveTo=8, framesAfter={"fill_inventory": EDITED})
    body = _second(out)
    assert body["step"] == "/lightningai/jobs/99/apply"
    assert {f["question"]: f["answer"] for f in body["fields"]}["First name"] == "Adaline"
    assert body["application_id"] == "app-remembered"


def test_leaving_a_page_with_nothing_changed_posts_nothing(tmp_path):
    assert len(_receipts(_run(tmp_path, tabs=TABS, leaveTo=8))) == 1


def test_leaving_without_a_receipt_asks_the_page_nothing(tmp_path):
    out = _run(tmp_path, tabs=TABS, leaveTo=8, stored={"widget.session": _armed_entry()})
    assert _receipts(out) == []
    assert not [msg for msg in out["broadcasts"] if msg["message"].get("readOnly")]
