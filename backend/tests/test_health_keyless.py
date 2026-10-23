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
