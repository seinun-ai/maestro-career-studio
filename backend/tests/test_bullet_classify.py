from app.services import bullet_classify as bc


def test_content_hash_normalizes_whitespace_and_case_sensitivity():
    assert bc.content_hash("Built  X ") == bc.content_hash("Built X")
    assert bc.content_hash("Built X") != bc.content_hash("built X")


def test_empty_text_classified_deterministically(db_session):
    out = bc.classify_items(db_session, [{"text": "", "hints": []}])
    (result,) = out.values()
    assert result["level"] == "unaddressed" and result["source"] == "deterministic"


def test_classify_uses_cache_and_only_calls_llm_for_misses(db_session, monkeypatch):
    calls = []

    def fake_llm(*, prompt, model, response_format, trace_name):
        import json
        import re
        items = json.loads(re.search(r"\[.*\]", prompt, re.S).group(0))
        calls.append([i["id"] for i in items])
        return {"classifications": [
            {"id": i["id"], "level": "adjacent", "reason": "r", "confidence": 0.9}
            for i in items
        ]}

    monkeypatch.setattr(bc.llm, "call_openai", fake_llm)
    monkeypatch.setattr(bc.model_settings, "get_smart_model", lambda s: "test-model")

    first = bc.classify_items(db_session, [{"text": "Built the ingestion service", "hints": []}])
    assert len(calls) == 1
    second = bc.classify_items(db_session, [{"text": "Built the ingestion service", "hints": []}])
    assert len(calls) == 1  # cache hit, no second call
    assert first == second


def test_invalid_level_from_llm_falls_back_to_uncertain(db_session, monkeypatch):
    # LLM returns a classification whose id doesn't match any pending item and whose
    # level is invalid → the item degrades to implied + uncertain (a question), never a guess.
    monkeypatch.setattr(bc.model_settings, "get_smart_model", lambda s: "test-model")
    monkeypatch.setattr(
        bc.llm, "call_openai",
        lambda **k: {"classifications": [{"id": "nope", "level": "amazing"}]},
    )
    out = bc.classify_items(db_session, [{"text": "Did various things", "hints": []}])
    (result,) = out.values()
    assert result["level"] == "implied" and result["uncertain"] is True


def test_override_wins(db_session, monkeypatch):
    monkeypatch.setattr(bc.model_settings, "get_smart_model", lambda s: "test-model")
    text = "Shipped X to 10 users"
    monkeypatch.setattr(bc.llm, "call_openai", lambda **k: {"classifications": [
        {"id": bc.content_hash(text), "level": "analogue", "reason": "", "confidence": 0.9}]})
    bc.classify_items(db_session, [{"text": text, "hints": []}])
    bc.set_override(db_session, bc.content_hash(text), "direct", "  I verified the outcome.  ")
    out = bc.classify_items(db_session, [{"text": text, "hints": []}])
    assert out[bc.content_hash(text)]["level"] == "direct"
    assert out[bc.content_hash(text)]["source"] == "override"
    assert out[bc.content_hash(text)]["reason"] == "I verified the outcome."

    row = db_session.get(bc.BulletClassification, bc.content_hash(text))
    assert row.override_reason == "I verified the outcome."

    bc.set_override(db_session, bc.content_hash(text), None, "ignored on clear")
    db_session.refresh(row)
    assert row.override_level is None
    assert row.override_reason is None


def test_zero_confidence_uncertain_is_stable_across_cache(db_session, monkeypatch):
    monkeypatch.setattr(bc.model_settings, "get_smart_model", lambda s: "test-model")
    text = "Did a thing"
    monkeypatch.setattr(bc.llm, "call_openai", lambda **k: {"classifications": [
        {"id": bc.content_hash(text), "level": "adjacent", "reason": "", "confidence": 0.0}]})
    first = bc.classify_items(db_session, [{"text": text, "hints": []}])
    second = bc.classify_items(db_session, [{"text": text, "hints": []}])
    assert first == second                                   # fresh == cache, determinism
    assert first[bc.content_hash(text)]["uncertain"] is True # 0.0 confidence stays uncertain
