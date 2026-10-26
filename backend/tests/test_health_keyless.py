"""The health check with no model key: stored judgments only, an ungraded report while bullets wait,
and a connected agent's judgments validated and stored by the app's own rubric.

No test here sets a key (conftest strips them), and `llm.call_openai` raises: a keyless run that
reaches a model is the bug."""
import pytest

from app.models.bullet_classification import BulletClassification
from app.services import bullet_classify as bc
from app.services import llm


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def unexpected(**kwargs):
        raise AssertionError(f"a keyless health check called a model: {kwargs.get('trace_name')}")

    monkeypatch.setattr(llm, "call_openai", unexpected)


SHIPPED = "Shipped the billing export to 40 finance teams, ending manual month-end reconciliation"
REDESIGNED = "Redesigned the onboarding flow for the mobile app"
VAGUE = "Worked on various data projects"


def _store(db, text, *, level="adjacent", model="gpt-old", rubric=bc.RUBRIC_VERSION):
    db.add(BulletClassification(content_hash=bc.content_hash(text), level=level, reason="r",
                                confidence=0.9, model=model, rubric_version=rubric,
                                evidence_json=[], language_json=[]))
    db.commit()


def _items(*texts):
    return [{"text": t, "hints": []} for t in texts]


# --------------------------------------------------------------------------- #
# stored_judgments


def test_stored_judgments_counts_any_judge_and_lists_the_rest_as_pending(db_session):
    _store(db_session, REDESIGNED, model="some-former-model")
    judged, pending = bc.stored_judgments(db_session, _items(REDESIGNED, VAGUE))
    assert judged[bc.content_hash(REDESIGNED)]["level"] == "adjacent"
    assert judged[bc.content_hash(REDESIGNED)]["judge"] == "some-former-model"
    assert pending == {bc.content_hash(VAGUE): {"id": bc.content_hash(VAGUE), "text": VAGUE,
                                                "hints": []}}


def test_stored_judgments_treats_an_older_rubric_as_pending(db_session):
    _store(db_session, REDESIGNED, rubric=bc.RUBRIC_VERSION - 1)
    judged, pending = bc.stored_judgments(db_session, _items(REDESIGNED))
    assert judged == {}
    assert list(pending) == [bc.content_hash(REDESIGNED)]


def test_stored_judgments_keeps_an_override_and_empty_text(db_session):
    bc.set_override(db_session, bc.content_hash(VAGUE), "implied", "my call")
    judged, pending = bc.stored_judgments(db_session, _items(VAGUE, ""))
    assert judged[bc.content_hash(VAGUE)]["source"] == "override"
    assert judged[bc.content_hash("")]["source"] == "deterministic"
    assert pending == {}


def test_evaluator_prompt_is_the_rubric_filled_with_the_pending_items(db_session):
    _, pending = bc.stored_judgments(db_session, _items(REDESIGNED, VAGUE))
    prompt = bc.evaluator_prompt(db_session, pending)
    assert "$items_json" not in prompt
    for chash in pending:
        assert chash in prompt
    assert "Return JSON only" in prompt


# --------------------------------------------------------------------------- #
# record_judgments


def test_agent_judge_names_the_client():
    assert bc.agent_judge(None) == "agent"
    assert bc.agent_judge("  ") == "agent"
    assert bc.agent_judge(" claude-ai ") == "agent:claude-ai"


def test_record_judgments_validates_and_stores_under_the_agent(db_session):
    chash = bc.content_hash(SHIPPED)
    accepted, rejected = bc.record_judgments(db_session, "agent:claude-ai", _items(SHIPPED), [{
        "id": chash, "level": "direct", "reason": "named adopters and effect",
        "evidence": ["ending manual month-end reconciliation"], "confidence": 0.9,
        "question": None, "ask_kind": None, "language": [],
    }])
    assert accepted == [{"id": chash, "level": "direct"}]
    assert rejected == []
    row = db_session.get(BulletClassification, chash)
    assert (row.level, row.model, row.rubric_version) == ("direct", "agent:claude-ai",
                                                           bc.RUBRIC_VERSION)
    assert row.evidence_json == ["ending manual month-end reconciliation"]


def test_record_judgments_demotes_a_level_without_a_verbatim_quote(db_session):
    chash = bc.content_hash(REDESIGNED)
    accepted, _ = bc.record_judgments(db_session, "agent", _items(REDESIGNED), [
        {"id": chash, "level": "direct", "evidence": ["made users much happier"],
         "confidence": 0.9}])
    assert accepted == [{"id": chash, "level": "adjacent"}]
    assert db_session.get(BulletClassification, chash).level == "adjacent"


def test_record_judgments_rejects_what_it_cannot_store(db_session):
    _store(db_session, REDESIGNED)
    vague = bc.content_hash(VAGUE)
    accepted, rejected = bc.record_judgments(db_session, "agent", _items(REDESIGNED, VAGUE), [
        {"id": bc.content_hash(REDESIGNED), "level": "implied"},   # already judged
        {"id": "0123456789abcdef", "level": "implied"},              # not in this resume
        {"id": vague, "level": "excellent"},                         # not a level
        "not an entry",
        {"id": vague, "level": "implied", "confidence": 0.8},
        {"id": vague, "level": "unaddressed"},                       # twice in one call
    ])
    assert accepted == [{"id": vague, "level": "implied"}]
    assert [r["id"] for r in rejected] == [
        bc.content_hash(REDESIGNED), "0123456789abcdef", vague, None, vague]
    assert all(r["reason"] for r in rejected)
    assert db_session.get(BulletClassification, bc.content_hash(REDESIGNED)).model == "gpt-old"
    assert db_session.get(BulletClassification, vague).level == "implied"


# --------------------------------------------------------------------------- #
# resume_lint: the keyless report

from app.services import resume_lint as rl  # noqa: E402

CUT = "Cut the nightly ETL runtime from 6 hours to 40 minutes by partitioning the fact tables"
SUMMARY = "Data analyst who builds reporting for finance teams."
BULLETS = [SHIPPED, REDESIGNED, VAGUE, CUT]


def _resume():
    return {
        "contact": {"name": "Sample Person", "email": "a@example.com", "phone": "555"},
        "summary": SUMMARY,
        "experience": [{"company": "Example Co", "role": "Analyst", "start_date": "Jan 2021",
                        "end_date": "Present", "bullets": list(BULLETS)}],
        "projects": [], "education": [], "skills": [],
    }


@pytest.fixture
def pass_gates(monkeypatch):
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, data: [
        {"id": g, "tier": "fatal", "status": "pass", "label": g, "detail": ""}
        for g in ("S1", "S2", "S4")])


def test_keyless_run_with_nothing_stored_is_ungraded_but_keeps_gates(db_session, pass_gates):
    row = rl.run_report(db_session, "base", "keyless", _resume())
    report = row.report_json
    assert (report["score"], report["grade"], report["next_grade"]) == (None, None, None)
    assert report["judged"] == {"done": 0, "pending": 5, "by": []}
    assert report["insufficient_evidence"] is False      # four scored bullets wait, not too few
    assert {g["id"] for g in report["gates"]} == {"S1", "S2", "S3", "S4", "S5"}   # no C1 yet
    assert row.features_json["raw_score"] is None
    assert row.features_json["n_scoreable"] == 4
    assert row.model is None
    assert not [f for f in report["findings"] if f["type"] in ("fix", "ask")
                and f["location"].get("bullet_index") is not None]


def test_keyless_run_grades_once_every_scored_bullet_is_stored(db_session, pass_gates):
    for text in BULLETS:
        _store(db_session, text, level="direct" if text != VAGUE else "implied",
               model="agent:claude-ai")
    _store(db_session, SUMMARY, level="adjacent", model="gpt-old")
    row = rl.run_report(db_session, "base", "keyless-graded", _resume())
    report = row.report_json
    assert isinstance(report["score"], int) and report["grade"] in "ABCDF"
    assert report["judged"] == {"done": 5, "pending": 0, "by": ["agent:claude-ai", "gpt-old"]}
    assert row.model is None                  # two judges: the report names them in `judged`


def test_keyless_run_with_only_the_summary_pending_grades_but_skips_c1(db_session, pass_gates):
    for text in BULLETS:
        _store(db_session, text, level="unaddressed", model="agent:claude-ai")
    row = rl.run_report(db_session, "base", "keyless-summary", _resume())
    report = row.report_json
    assert report["grade"] is not None
    assert report["judged"]["pending"] == 1
    assert "C1" not in {g["id"] for g in report["gates"]}   # the summary is hot and unjudged
    assert row.model == "agent:claude-ai"


def test_use_llm_false_reads_stored_judgments(db_session, pass_gates):
    for text in [*BULLETS, SUMMARY]:
        _store(db_session, text, level="direct", model="gpt-old")
    row = rl.run_report(db_session, "base", "no-llm", _resume(), use_llm=False)
    assert row.report_json["score"] == 100


def test_gain_divides_by_every_scored_bullet_judged_or_not():
    resume = _resume()
    levels = {("experience", 0, 0): {"level": "adjacent", "value": 0.5, "reason": "",
                                     "confidence": 1.0, "source": "cache", "uncertain": False},
              ("experience", 0, 1): {"level": "direct", "value": 1.0, "reason": "",
                                     "confidence": 1.0, "source": "cache", "uncertain": False}}
    out = rl.assemble(resume, levels, [], "experienced", set(),
                      pending=[("experience", 0, 2), ("experience", 0, 3)],
                      rewrite_fn=lambda t: None)
    ask = next(f for f in out["report"]["findings"] if f["location"].get("bullet_index") == 0)
    assert ask["gain"] == round(100 * (0.8 - 0.5) / 4)
    assert out["report"]["score"] is None
    assert out["features"]["n_scoreable"] == 4


def test_judging_brief_hands_over_the_pending_bullets(db_session):
    resume = _resume()
    for text in [*BULLETS, SUMMARY]:
        _store(db_session, text)
    assert rl.judging_brief(db_session, resume) is None

    resume["experience"][0]["bullets"].append("Responsible for weekly reports")
    brief = rl.judging_brief(db_session, resume)
    new_id = bc.content_hash("Responsible for weekly reports")
    assert brief["pending_ids"] == [new_id]
    assert brief["rubric_version"] == bc.RUBRIC_VERSION
    assert new_id in brief["prompt"] and "weak_opener" in brief["prompt"]


def test_record_judgments_reads_the_resumes_own_bullets(db_session):
    resume = _resume()
    accepted, rejected = rl.record_judgments(db_session, resume, "agent:codex", [
        {"id": bc.content_hash(VAGUE), "level": "implied", "confidence": 0.7}])
    assert accepted == [{"id": bc.content_hash(VAGUE), "level": "implied"}]
    assert rejected == []


# --------------------------------------------------------------------------- #
# REST: the run, the judging brief, the judgments write

from app.models.base_resume import BaseResume  # noqa: E402

MCP_CLAUDE = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}


@pytest.fixture
def seeded(db_session, pass_gates):
    db_session.add(BaseResume(slug="keyless", display_name="Keyless", data_json=_resume()))
    db_session.commit()
    return "keyless"


def _entry(text, level="direct", **extra):
    return {"id": bc.content_hash(text), "level": level, "confidence": 0.9,
            "evidence": [" ".join(text.split()[:4])], "reason": "r", **extra}


def test_run_without_a_key_returns_an_ungraded_report_and_the_brief(client, seeded):
    response = client.post(f"/api/resume-lint/base/{seeded}/run")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["score"], body["grade"], body["next_grade"]) == (None, None, None)
    assert body["judged"] == {"done": 0, "pending": 5, "by": []}
    assert body["score_breakdown"] is None
    brief = body["judging"]
    assert brief["rubric_version"] == bc.RUBRIC_VERSION
    assert len(brief["pending_ids"]) == 5
    assert all(pid in brief["prompt"] for pid in brief["pending_ids"])

    latest = client.get(f"/api/resume-lint/base/{seeded}").json()
    assert latest["judged"]["pending"] == 5 and latest["grade"] is None


def test_judgments_from_an_agent_grade_the_report(client, db_session, seeded):
    entries = [_entry(t, "implied" if t == VAGUE else "direct") for t in [*BULLETS, SUMMARY]]
    response = client.post(f"/api/resume-lint/base/{seeded}/judgments",
                           json={"classifications": entries}, headers=MCP_CLAUDE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["accepted"]) == 5 and body["rejected"] == []
    assert isinstance(body["score"], int) and body["grade"] in "ABCDF"
    assert body["judged"] == {"done": 5, "pending": 0, "by": ["agent:claude-ai"]}
    assert body["judging"] is None
    assert body["model"] == "agent:claude-ai"
    assert db_session.get(BulletClassification, bc.content_hash(CUT)).model == "agent:claude-ai"


def test_partial_judgments_leave_the_rest_in_the_brief(client, seeded):
    response = client.post(f"/api/resume-lint/base/{seeded}/judgments",
                           json={"classifications": [_entry(CUT), _entry(VAGUE, "ok")]})
    body = response.json()
    assert [a["id"] for a in body["accepted"]] == [bc.content_hash(CUT)]
    assert [r["id"] for r in body["rejected"]] == [bc.content_hash(VAGUE)]
    assert body["grade"] is None and body["judged"]["pending"] == 4
    assert bc.content_hash(CUT) not in body["judging"]["pending_ids"]
    assert body["judged"]["by"] == ["agent"]          # no MCP origin header: a nameless agent


def test_judgments_are_refused_while_a_model_key_is_set(client, db_session, seeded, monkeypatch):
    # The web's request: Maestro's model judges then. An agent app that writes judges its own
    # even with a key set (test_resume_lint_router.py, "who writes").
    monkeypatch.setattr(llm, "any_model_key_configured", lambda: True)
    response = client.post(f"/api/resume-lint/base/{seeded}/judgments",
                           json={"classifications": [_entry(CUT)]})
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A model key is set, so Maestro judges the bullets with its own model. "
        "Run the health check instead.")
    assert db_session.get(BulletClassification, bc.content_hash(CUT)) is None
