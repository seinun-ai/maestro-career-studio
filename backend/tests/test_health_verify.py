"""Finding-verifier tests: the model may veto or annotate rule detections,
never create them; verdicts are cached by payload hash for deterministic re-runs;
any LLM failure passes detections through unchanged."""
import pytest

from app.services import health_verify as hv

GAP = {"after": "Fictional Employer Legacy", "before": "Fictional Employer 3", "months": 24,
       "covered_months": 21, "uncovered_months": 3}
C2 = {"claimed_years": 8, "actual_years": 3.0}
RESUME = {"summary": "s", "experience": [], "education": []}


@pytest.fixture
def _model(monkeypatch):
    monkeypatch.setattr(hv.model_settings, "get_smart_model", lambda db: "test-model")


def _patch_llm(monkeypatch, response=None, error=None):
    calls = {"n": 0}

    def fake(**kwargs):
        calls["n"] += 1
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(hv.llm, "call_openai", fake)
    return calls


def test_veto_drops_gap(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "gap:0", "verdict": "veto", "context": ""}]})
    gaps, c2, cache = hv.verify_detections(db_session, RESUME, [dict(GAP)], None)
    assert gaps == []
    assert c2 is None
    assert cache[hv._payload_hash("gap", GAP)]["verdict"] == "veto"


def test_keep_keeps_gap(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "gap:0", "verdict": "keep", "context": ""}]})
    gaps, _, _ = hv.verify_detections(db_session, RESUME, [dict(GAP)], None)
    assert gaps == [GAP]
    assert "context" not in gaps[0]


def test_context_annotates_gap(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "gap:0", "verdict": "keep", "context": "M.S. covers most of this."}]})
    original = dict(GAP)
    gaps, _, _ = hv.verify_detections(db_session, RESUME, [original], None)
    assert gaps[0]["context"] == "M.S. covers most of this."
    assert "context" not in original  # annotation is a copy, input untouched


def test_c2_veto_returns_none(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "c2", "verdict": "veto", "context": ""}]})
    gaps, c2, cache = hv.verify_detections(db_session, RESUME, [], dict(C2))
    assert gaps == []
    assert c2 is None
    assert cache[hv._payload_hash("c2", C2)]["verdict"] == "veto"


def test_c2_context_annotates(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "c2", "verdict": "keep", "context": "Claim is domain-scoped."}]})
    _, c2, _ = hv.verify_detections(db_session, RESUME, [], dict(C2))
    assert c2["context"] == "Claim is domain-scoped."
    assert c2["claimed_years"] == 8


def test_prior_cache_hit_skips_llm(db_session, monkeypatch, _model):
    calls = _patch_llm(monkeypatch, {"verdicts": []})
    prior = {hv._payload_hash("gap", GAP): {"verdict": "veto", "context": ""}}
    gaps, _, cache = hv.verify_detections(
        db_session, RESUME, [dict(GAP)], None, prior_cache=prior)
    assert calls["n"] == 0
    assert gaps == []  # cached veto still applies
    assert cache == prior  # verdict carried forward for the next run


def test_llm_failure_passes_detections_through(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, error=RuntimeError("boom"))
    gaps, c2, cache = hv.verify_detections(db_session, RESUME, [dict(GAP)], dict(C2))
    assert gaps == [GAP]
    assert c2 == C2
    assert all(v["verdict"] == "keep" for v in cache.values())


def test_malformed_verdicts_default_to_keep(db_session, monkeypatch, _model):
    _patch_llm(monkeypatch, {"verdicts": [
        {"id": "no-such-id", "verdict": "veto"},          # unknown id → ignored
        {"id": "c2", "verdict": "nuke", "context": None},  # invalid verdict → keep
        "not-a-dict",
    ]})
    gaps, c2, _ = hv.verify_detections(db_session, RESUME, [dict(GAP)], dict(C2))
    assert gaps == [GAP]
    assert c2 == C2


def test_empty_detections_no_llm_call(db_session, monkeypatch, _model):
    calls = _patch_llm(monkeypatch, {"verdicts": []})
    gaps, c2, cache = hv.verify_detections(db_session, RESUME, [], None)
    assert (gaps, c2, cache) == ([], None, {})
    assert calls["n"] == 0
