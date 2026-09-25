import pytest

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
        items = json.JSONDecoder().raw_decode(prompt.split("Items (JSON):", 1)[1].lstrip())[0]
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


TEXT = "Automated invoice processing time checks so finance could close the ledger"


def assessment(**changes):
    return dict({"level": "direct", "evidence": ["finance could close the ledger"],
                 "reason": "Finance can close", "question": None, "ask_kind": None,
                 "measure_target": None, "alt_question": None, "confidence": 0.9,
                 "language": []}, **changes)


def test_qualitative_direct_has_full_credit_and_no_question():
    result = bc._validate(TEXT, assessment(question="What changed?", ask_kind="detail"))
    assert result["level"] == "direct"
    assert result["question"] is None and result["ask_kind"] is None
    assert not any(ch.isdigit() for ch in TEXT)


@pytest.mark.parametrize("evidence", [["made something else much better"], ["the"], ["finance could"], "finance could close the ledger"])
def test_unsupported_or_trivial_evidence_cannot_back_high_level(evidence):
    assert bc._validate(TEXT, assessment(evidence=evidence))["level"] == "adjacent"


@pytest.mark.parametrize("changes,question", [
    ({"measure_target": None}, "What did finance stop doing by hand?"),
    ({"alt_question": None}, None),
    ({"measure_target": "customer satisfaction"}, "What did finance stop doing by hand?"),
    ({"alt_question": "How many invoices?"}, None),
    ({"metric_unavailable": True}, "What did finance stop doing by hand?"),
    ({"ask_kind": "detail"}, "What did finance stop doing by hand?"),
])
def test_invalid_number_asks_are_demoted_with_number_question_removed(changes, question):
    entry = assessment(level="analogue", question="How much processing time was saved?", ask_kind="measure",
                       measure_target="invoice processing time", alt_question="What did finance stop doing by hand?")
    entry.update(changes)
    result = bc._validate(TEXT, entry)
    assert result["ask_kind"] == "detail"
    assert result["question"] == question
    assert result["measure_target"] is None and result["alt_question"] is None


def test_whole_word_target_and_stored_metric_unavailable():
    entry = assessment(level="analogue", question="How much?", ask_kind="measure", measure_target="rate",
                       alt_question="What became easier?")
    assert bc._validate("Built an accurate processing system", entry)["ask_kind"] == "detail"
    entry["measure_target"] = "invoice processing time"
    assert bc._validate(TEXT, entry)["ask_kind"] == "measure"
    assert bc._validate(TEXT, entry, metric_unavailable=True)["ask_kind"] == "detail"


@pytest.mark.parametrize("level", [[], {}, None, 42])
def test_malformed_level_returns_none(level):
    assert bc._validate(TEXT, assessment(level=level)) is None


@pytest.mark.parametrize("value", ["high", float("nan"), float("inf"), {}, []])
def test_malformed_confidence_is_zero(value):
    assert bc._validate(TEXT, assessment(confidence=value))["confidence"] == 0


def test_malformed_question_and_language_degrade_safely():
    result = bc._validate(TEXT, assessment(level="adjacent", question=42, language={"span": "a"}))
    assert result["question"] is None and result["ask_kind"] == "detail"
    assert result["language"] == []
    result = bc._validate(TEXT, assessment(language=[{"span": "invented", "fix": "x"},
                                                   {"span": "checks", "fix": "check"}, None]))
    assert result["language"] == [{"span": "checks", "fix": "check"}]


@pytest.mark.parametrize("raw", [None, [], "bad", {"classifications": {}},
                                  {"classifications": [{"id": [], "level": "direct"}]}])
def test_bad_batch_shape_degrades_without_exception(db_session, monkeypatch, raw):
    monkeypatch.setattr(bc.llm, "call_openai", lambda **kw: raw)
    result = bc.classify_items(db_session, [{"text": TEXT}])[bc.content_hash(TEXT)]
    assert result["level"] == "implied" and result["uncertain"]


def test_cache_projects_fields_and_invalidates_version_and_model(db_session, monkeypatch):
    calls = []
    model = ["model-a"]
    monkeypatch.setattr(bc.model_settings, "get_smart_model", lambda db: model[0])
    def fake(**kw):
        calls.append(kw)
        return {"classifications": [{"id": bc.content_hash(TEXT), **assessment()}]}
    monkeypatch.setattr(bc.llm, "call_openai", fake)
    first = bc.classify_items(db_session, [{"text": TEXT}])
    assert first[bc.content_hash(TEXT)]["evidence"] == ["finance could close the ledger"]
    assert first == bc.classify_items(db_session, [{"text": TEXT}])
    assert len(calls) == 1
    row = db_session.get(bc.BulletClassification, bc.content_hash(TEXT))
    row.rubric_version -= 1
    db_session.commit()
    bc.classify_items(db_session, [{"text": TEXT}])
    assert len(calls) == 2
    model[0] = "model-b"
    bc.classify_items(db_session, [{"text": TEXT}])
    assert len(calls) == 3
    bc.set_override(db_session, bc.content_hash(TEXT), "direct", "verified")
    model[0] = "model-c"
    row.rubric_version = 1
    db_session.commit()
    result = bc.classify_items(db_session, [{"text": TEXT}])[bc.content_hash(TEXT)]
    assert len(calls) == 3
    assert result["source"] == "override" and result["question"] is None


def test_evaluation_only_seam_does_not_write_ordinary_cache(db_session, monkeypatch):
    key = bc.content_hash(TEXT)
    monkeypatch.setattr(bc.llm, "call_openai", lambda **kw: {"classifications": [{"id": key, **assessment()}]})
    results = bc._evaluate_batch(db_session, {key: {"id": key, "text": TEXT}})
    assert results[key]["level"] == "direct"
    assert db_session.get(bc.BulletClassification, key) is None


@pytest.mark.parametrize('ask_kind', [None, [], {}, 'other'])
def test_missing_or_invalid_ask_kind_cannot_smuggle_number_question(ask_kind):
    result = bc._validate(TEXT, assessment(level='adjacent', ask_kind=ask_kind,
                                           question='How many invoices?'))
    assert result['ask_kind'] == 'detail'
    assert result['question'] is None
